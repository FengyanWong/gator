// The page's entry point (the workbench's first build): App drawn into the root element under the outer crash panel
// (record 7.188), with the page's two style sheets.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { CrashPanel } from './panels/CrashPanel';
import { APP_ROOT_ID } from './contract';
import './styles.css';
import './roadster.css';

// The outer crash panel (record 7.188): around everything, for a failure above App's own one; it has no Undo to offer.
createRoot(document.getElementById(APP_ROOT_ID)!).render(<React.StrictMode><CrashPanel><App /></CrashPanel></React.StrictMode>);
