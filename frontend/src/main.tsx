import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { CrashPanel } from './panels/CrashPanel';
import './styles.css';
import './themes.css';

// The outer crash panel (record 7.188): around everything, for a failure above App's own one; it has no Undo to offer.
createRoot(document.getElementById('root')!).render(<React.StrictMode><CrashPanel><App /></CrashPanel></React.StrictMode>);
