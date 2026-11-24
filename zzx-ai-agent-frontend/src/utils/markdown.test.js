import { describe, expect, it } from 'vitest'

import { renderSafeMarkdown } from './markdown.js'


describe('secure markdown rendering', () => {
  it('keeps approved links and hardens new tabs', () => {
    const html = renderSafeMarkdown('[官网](https://example.com)')
    expect(html).toContain('href="https://example.com"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it.each([
    '[危险](javascript:alert(1))',
    '[混淆](java&#x73;cript:alert(1))',
    '[数据](data:text/html,hello)',
    '[相对地址](/admin)'
  ])('does not emit a link for an unapproved URL: %s', source => {
    const html = renderSafeMarkdown(source)
    expect(html).not.toContain('<a ')
    expect(html).not.toMatch(/href=/i)
  })

  it('does not execute raw HTML embedded in model output', () => {
    const html = renderSafeMarkdown('<img src=x onerror=alert(1)><script>alert(1)</script>')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('<script')
    expect(html).toContain('&lt;img')
    expect(html).toContain('&lt;script&gt;')
  })
})
