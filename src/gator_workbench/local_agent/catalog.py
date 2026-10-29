"""Pinned NVIDIA weights and upstream runtime assets, checked on 2026-10-29.

Only this catalog can supply download URLs, filenames or runtime arguments. A model
reply and the browser cannot add entries or nominate an executable.
"""
from dataclasses import asdict, dataclass

GiB = 1024 ** 3


@dataclass(frozen=True)
class Model:
    id: str
    name: str
    repo: str
    revision: str
    filename: str
    size: int
    sha256: str
    template: str
    vram_gib: float
    ram_gib: float
    description: str

    @property
    def url(self):
        return f'https://huggingface.co/{self.repo}/resolve/{self.revision}/{self.filename}'

    def public(self):
        return dict(asdict(self), provider='NVIDIA', source=f'https://huggingface.co/{self.repo}',
                    context_tokens=8192, runtime='llama.cpp b11669 · Windows x64 CUDA 12.4 (also through WSL)',
                    free_ram_gib=6, generation='Uncapped; context shifting; loads per reply')


CATALOG = {
    m.id: m for m in (
        Model('bolt-74b', 'Nemotron 3.5 Bolt 74B-A9B 24GB',
              'nvidia/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-24GB-GGUF',
              'e0fecb69cb3e5e4c5e8a056fa2aec98c78e91246',
              'NVIDIA-Nemotron-3.5-Bolt-74B-A9B-24GB.gguf', 22018326528,
              '91d63363e782c8a3d5f4be42816eba8e0d42dd2530bd07a7d0d2dc440599af75',
              'chatml', 22, 28,
              'Local 74B mixture-of-experts model, tested on an RTX 4090. NVIDIA quantization.'),
        Model('bolt-e4b', 'Nemotron 3.5 Bolt E4B 4GB',
              'nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB',
              '1db54d5b12533ff1bcaa8e42cf4c667988a1f1be',
              'Nemotron-3.5-Bolt-E4B-Q4_K_M.gguf', 6180446208,
              'c8af2b8aea10a690a1d9491db744a9446660173cb38fc489612b556615a69612',
              'gemma', 8, 16,
              'Smaller NVIDIA model. This published GGUF is 6.18 GB; the product name is not its download size.'),
    )
}

# Both archives are needed: runtime plus CUDA DLLs. Never use an unpinned "latest" URL.
RUNTIME_ASSETS = (
    ('llama-b11669-bin-win-cuda-12.4-x64.zip', 266582698,
     'c2da1f73ed176ae093ac5aceb978a7b167a16113f6d74c6789eeaee2135cb8dc'),
    ('cudart-llama-bin-win-cuda-12.4-x64.zip', 391443627,
     '8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6'),
)
RUNTIME_URL = 'https://github.com/ggml-org/llama.cpp/releases/download/b11669/'
