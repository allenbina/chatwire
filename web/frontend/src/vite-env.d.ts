/// <reference types="vite/client" />

import type { chatwire as ChawtireAPI } from './plugins/registry'

declare global {
  interface Window {
    /**
     * Public chatwire plugin API. Available on window once the React app
     * boots. External plugin bundles loaded via <script> tags call this
     * to register slot components:
     *
     *   window.chatwire.registerSlot('sidebar.panel', MyWidget)
     */
    chatwire?: typeof ChawtireAPI
  }
}
