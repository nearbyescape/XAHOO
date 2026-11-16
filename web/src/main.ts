import './app.css';
import App from './App.svelte';
import { installGlobalReporting } from './lib/report';

installGlobalReporting();
const app = new App({ target: document.getElementById('app')! });
export default app;
