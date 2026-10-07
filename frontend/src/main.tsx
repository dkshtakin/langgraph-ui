import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

// StrictMode is deliberately absent. React mounts every component twice under
// it, and each mount of the streaming hook opens two event streams that a
// StrictMode-only unmount never closes — the browser allows six connections to
// one origin, so two graph switches are enough to wedge the whole app until the
// tab is closed. Put StrictMode back once @langchain/react handles a double
// mount; the crash it hides is not this app's to fix.
createRoot(document.getElementById('root')!).render(<App />)
