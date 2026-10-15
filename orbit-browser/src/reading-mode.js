/**
 * JARVIS Orbit — Reading Mode
 * 
 * Distraction-free reading view inspired by Arc's Reader mode.
 * Strips ads, navigation, and sidebars to show clean article content.
 */

(function() {
  'use strict';

  const READING_CSS = `
    * { all: unset !important; }
    
    body {
      display: flex !important;
      flex-direction: column !important;
      align-items: center !important;
      max-width: 720px !important;
      margin: 0 auto !important;
      padding: 40px 24px !important;
      background: #0a0a0a !important;
      color: #e0e0e0 !important;
      font-family: Georgia, 'Times New Roman', serif !important;
      font-size: 18px !important;
      line-height: 1.8 !important;
    }
    
    h1, h2, h3, h4 { 
      color: #ffffff !important;
      font-weight: 600 !important;
      margin: 1.5em 0 0.5em !important;
      line-height: 1.3 !important;
    }
    h1 { font-size: 32px !important; }
    h2 { font-size: 24px !important; }
    h3 { font-size: 20px !important; }
    
    p { margin: 0 0 1.2em !important; }
    
    a { color: #60a5fa !important; text-decoration: underline !important; }
    a:hover { color: #93c5fd !important; }
    
    img { max-width: 100% !important; height: auto !important; border-radius: 8px !important; margin: 1em 0 !important; }
    
    blockquote {
      border-left: 3px solid #444 !important;
      padding-left: 16px !important;
      margin: 1em 0 !important;
      color: #aaa !important;
      font-style: italic !important;
    }
    
    code, pre {
      background: #1a1a1a !important;
      padding: 2px 6px !important;
      border-radius: 4px !important;
      font-family: 'Geist Mono', monospace !important;
      font-size: 0.9em !important;
    }
    pre { padding: 16px !important; overflow-x: auto !important; }
    
    table { border-collapse: collapse !important; width: 100% !important; margin: 1em 0 !important; }
    th, td { border: 1px solid #333 !important; padding: 8px 12px !important; text-align: left !important; }
    th { background: #1a1a1a !important; font-weight: 600 !important; }
    
    ul, ol { padding-left: 1.5em !important; margin: 0 0 1em !important; }
    li { margin: 0.3em 0 !important; }
    
    .orbit-reader-bar {
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      right: 0 !important;
      display: flex !important;
      align-items: center !important;
      justify-content: space-between !important;
      padding: 8px 16px !important;
      background: rgba(0,0,0,0.9) !important;
      backdrop-filter: blur(12px) !important;
      border-bottom: 1px solid #222 !important;
      z-index: 9999 !important;
      font-family: -apple-system, sans-serif !important;
      font-size: 13px !important;
    }
    .orbit-reader-bar button {
      padding: 6px 12px !important;
      border: 1px solid #444 !important;
      border-radius: 6px !important;
      background: #1a1a1a !important;
      color: #ccc !important;
      cursor: pointer !important;
      font-size: 12px !important;
    }
    .orbit-reader-bar button:hover {
      background: #333 !important;
      color: #fff !important;
    }
    .orbit-reader-bar .reader-title {
      color: #888 !important;
      max-width: 400px !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
      white-space: nowrap !important;
    }
  `;

  class ReadingMode {
    constructor() {
      this.active = false;
      this.originalContent = null;
      this.originalStyles = [];
      this.webview = null;
    }

    /**
     * Toggle reading mode for the current page
     */
    async toggle() {
      if (this.active) {
        this.exit();
      } else {
        await this.enter();
      }
    }

    /**
     * Enter reading mode
     */
    async enter() {
      this.webview = document.querySelector('webview:not(.hidden)');
      if (!this.webview) {
        console.warn('[READER] No active webview');
        return;
      }

      try {
        // Extract main content
        const content = await this._extractContent();
        if (!content || !content.text || content.text.length < 100) {
          console.warn('[READER] Page content too short for reading mode');
          return;
        }

        // Inject reading mode
        await this._injectReadingMode(content);
        this.active = true;
        
        // Emit event
        window.dispatchEvent(new CustomEvent('reading-mode', { detail: { active: true } }));
        console.log('[READER] Reading mode activated');
      } catch (error) {
        console.error('[READER] Failed to enter reading mode:', error);
      }
    }

    /**
     * Exit reading mode
     */
    exit() {
      if (this.webview) {
        this.webview.reload();
      }
      this.active = false;
      window.dispatchEvent(new CustomEvent('reading-mode', { detail: { active: false } }));
      console.log('[READER] Reading mode deactivated');
    }

    /**
     * Extract main content from the page
     */
    async _extractContent() {
      return this.webview.executeJavaScript(`
        (function() {
          // Try common article selectors
          const selectors = [
            'article', '[role="main"]', 'main',
            '.post-content', '.article-content', '.entry-content',
            '.story-body', '.article-body', '.post-body',
            '#content', '#article', '#main-content',
          ];
          
          let article = null;
          for (const sel of selectors) {
            article = document.querySelector(sel);
            if (article && article.textContent.trim().length > 200) break;
          }
          
          // Fallback: find largest text block
          if (!article) {
            let maxLen = 0;
            for (const el of document.querySelectorAll('div, section')) {
              const text = el.textContent.trim();
              if (text.length > maxLen && text.length > 500) {
                // Check it's mostly text, not navigation
                const linkRatio = el.querySelectorAll('a').length / (el.querySelectorAll('*').length || 1);
                if (linkRatio < 0.3) {
                  maxLen = text.length;
                  article = el;
                }
              }
            }
          }
          
          if (!article) return null;
          
          // Extract structured content
          const title = document.querySelector('h1')?.textContent?.trim() || document.title;
          const byline = document.querySelector('[class*="author"], [class*="byline"], [rel="author"]')?.textContent?.trim();
          const date = document.querySelector('time')?.getAttribute('datetime') || document.querySelector('time')?.textContent?.trim();
          
          // Clean HTML
          let html = article.innerHTML;
          // Remove scripts, styles, iframes, ads
          html = html.replace(/<script[^>]*>[\\s\\S]*?<\\/script>/gi, '');
          html = html.replace(/<style[^>]*>[\\s\\S]*?<\\/style>/gi, '');
          html = html.replace(/<iframe[^>]*>[\\s\\S]*?<\\/iframe>/gi, '');
          html = html.replace(/<noscript[^>]*>[\\s\\S]*?<\\/noscript>/gi, '');
          html = html.replace(/class="[^"]*(?:ad|banner|popup|modal|sidebar|nav|footer|header)[^"]*"/gi, '');
          
          return {
            title,
            byline,
            date,
            html: html.slice(0, 50000),
            text: article.textContent.trim().slice(0, 10000),
            wordCount: article.textContent.trim().split(/\\s+/).length,
            url: location.href,
          };
        })()
      `);
    }

    /**
     * Inject reading mode into the webview
     */
    async _injectReadingMode(content) {
      const readingHtml = `
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>${content.title || 'Reading Mode'}</title>
          <style>${READING_CSS}</style>
        </head>
        <body>
          <div class="orbit-reader-bar">
            <button onclick="window._exitReader()">✕ Exit Reader</button>
            <span class="reader-title">${content.title || 'Article'}</span>
            <span style="color:#666">${content.wordCount || 0} words</span>
          </div>
          ${content.byline ? '<p style="color:#888;font-size:14px;margin-top:48px">By ' + content.byline + '</p>' : ''}
          ${content.date ? '<p style="color:#666;font-size:13px">' + content.date + '</p>' : ''}
          <article>${content.html}</article>
          <script>
            window._exitReader = function() {
              window.location.reload();
            };
          </script>
        </body>
        </html>
      `;

      // Navigate to a data URL with the reading mode content
      // Note: This replaces the page content entirely
      await this.webview.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(readingHtml)}`);
    }
  }

  // ── Expose to window ──────────────────────────────────────────
  window.readingMode = new ReadingMode();

  console.log('[READER] Reading Mode loaded — toggle with Ctrl+Shift+R or sidebar button');

})();
