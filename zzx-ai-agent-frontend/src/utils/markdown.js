import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'


const allowedProtocols = new Set(['http:', 'https:', 'mailto:'])
const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true
})

// First gate: reject unsafe and relative URLs before markdown-it emits a tag.
markdown.validateLink = (url) => {
  const candidate = String(url || '').trim()
  const scheme = candidate.match(/^([a-z][a-z0-9+.-]*:)/i)?.[1]?.toLowerCase()
  return Boolean(scheme && allowedProtocols.has(scheme))
}

const defaultLinkOpen = markdown.renderer.rules.link_open ||
  ((tokens, index, options, _env, renderer) => renderer.renderToken(tokens, index, options))
markdown.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, index, options, env, renderer)
}

export function renderSafeMarkdown(content) {
  const rendered = markdown.render(String(content || ''))
  // Second gate: sanitize the complete HTML even when parser configuration is
  // changed later. Only the explicitly approved URI schemes survive.
  const sanitized = DOMPurify.sanitize(rendered, {
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):)/i,
    ADD_ATTR: ['target', 'rel']
  })

  // DOMPurify may deliberately remove navigation attributes in stricter
  // environments. Re-apply them only after sanitization and only to links
  // whose final parsed protocol still passes the whitelist.
  const template = document.createElement('template')
  template.innerHTML = sanitized
  template.content.querySelectorAll('a[href]').forEach(link => {
    try {
      const protocol = new URL(link.getAttribute('href')).protocol.toLowerCase()
      if (!allowedProtocols.has(protocol)) {
        link.removeAttribute('href')
        return
      }
      link.setAttribute('target', '_blank')
      link.setAttribute('rel', 'noopener noreferrer')
    } catch {
      link.removeAttribute('href')
    }
  })
  return template.innerHTML
}
