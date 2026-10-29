"""Streaming, pinned downloads and verification. No model-selected URLs or commands."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import urllib.request
from uuid import uuid4
import zipfile

from .catalog import RUNTIME_ASSETS, RUNTIME_URL
from .runtime import Cancelled, Runtime


def verify_file(path, size, digest, cancel, progress):
    if path.stat().st_size != size:
        raise ValueError('The local file size does not match the pinned NVIDIA artifact.')
    hasher, read = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while chunk := stream.read(8 * 1024**2):
            if cancel.is_set():
                raise Cancelled()
            hasher.update(chunk)
            read += len(chunk)
            progress('Verifying SHA-256', read, size)
    if hasher.hexdigest() != digest:
        raise ValueError('SHA-256 verification failed; the file was not installed.')


def download(url, path, size, digest, cancel, progress):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.partial')
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'GATOR-local-agent/1'})
        with urllib.request.urlopen(request, timeout=20) as response, temporary.open('wb') as stream:
            if not response.url.startswith('https://'):
                raise ValueError('Refused a non-HTTPS download redirect.')
            length = response.headers.get('Content-Length')
            if length and int(length) != size:
                raise ValueError('Download size differs from the pinned artifact.')
            read, hasher = 0, hashlib.sha256()
            while chunk := response.read1(1024**2):
                if cancel.is_set():
                    raise Cancelled()
                read += len(chunk)
                if read > size:
                    raise ValueError('Download exceeded the pinned artifact size.')
                stream.write(chunk)
                hasher.update(chunk)
                progress('Downloading ' + path.name, read, size)
            stream.flush()
            os.fsync(stream.fileno())
        if read != size or hasher.hexdigest() != digest:
            raise ValueError('Incomplete download or SHA-256 mismatch; installation was not published.')
        if cancel.is_set():
            raise Cancelled()
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def install_runtime(root, cancel, progress):
    root = root.resolve()
    folder = root / ('runtime-install-' + uuid4().hex)
    folder.mkdir()
    try:
        for filename, size, digest in RUNTIME_ASSETS:
            archive = folder / filename
            download(RUNTIME_URL + filename, archive, size, digest, cancel, progress)
            with zipfile.ZipFile(archive) as zipped:
                if sum(item.file_size for item in zipped.infolist()) > 2 * 1024**3:
                    raise ValueError('Runtime archive expands beyond the installation allowance.')
                for item in zipped.infolist():
                    if cancel.is_set():
                        raise Cancelled()
                    destination = (folder / item.filename).resolve()
                    if not destination.is_relative_to(folder) or (item.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Runtime archive contains an unsafe path.')
                    zipped.extract(item, folder)
            archive.unlink()
        found = list(folder.rglob('llama-completion.exe'))
        if len(found) != 1:
            raise ValueError('Runtime archive did not contain exactly one completion executable.')
        Runtime(found[0]).verify()
        relative = found[0].relative_to(folder)
        destination = root / 'runtime-b11669'
        if destination.exists():
            raise ValueError('A runtime folder already exists. Check the operator runtime setting before replacing it.')
        if cancel.is_set():
            raise Cancelled()
        folder.replace(destination)
        return Runtime(destination / relative)
    finally:
        # The only recursive cleanup is this invocation's random staging directory.
        if folder.exists() and not folder.is_symlink() and folder.resolve().parent == root:
            shutil.rmtree(folder)
