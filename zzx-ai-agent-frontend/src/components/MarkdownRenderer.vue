<template>
  <div class="markdown-body" v-html="html"></div>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
  content: { type: String, default: "" }
})

const html = computed(() => renderMarkdown(props.content || ""))

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

function inline(text) {
  let t = text
  // Inline code (must come first)
  t = t.replace(/`([^`]+)`/g, "<code>$1</code>")
  // Bold **text**
  t = t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
  // Italic *text*  (but not ** already handled)
  t = t.replace(/\*(?!\*)(.+?)\*/g, "<em>$1</em>")
  // Links [text](url)
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
  return t
}

function renderMarkdown(text) {
  if (!text) return ""
  const escaped = escapeHtml(text.trim())
  const lines = escaped.split("\n")

  const out = []
  let inList = null      // "ol" | "ul" | null
  let inCodeBlock = false

  for (let i = 0; i < lines.length; i++) {
    let raw = lines[i]
    const trimmed = raw.trim()

    // ---------- code block toggle ----------
    if (trimmed.startsWith("```")) {
      if (inCodeBlock) {
        out.push("</code></pre>")
        inCodeBlock = false
      } else {
        if (inList) { out.push("</" + inList + ">"); inList = null }
        out.push("<pre><code>")
        inCodeBlock = true
      }
      continue
    }
    if (inCodeBlock) {
      out.push(trimmed + "\n")
      continue
    }

    // ---------- empty line ----------
    if (!trimmed) {
      if (inList) { out.push("</" + inList + ">"); inList = null }
      continue
    }

    // ---------- heading ----------
    const hMatch = trimmed.match(/^(#{1,3})\s+(.+)/)
    if (hMatch) {
      if (inList) { out.push("</" + inList + ">"); inList = null }
      const level = hMatch[1].length
      out.push("<h" + (level + 1) + ">" + inline(hMatch[2]) + "</h" + (level + 1) + ">")
      continue
    }

    // ---------- horizontal rule ----------
    if (/^-{3,}$/.test(trimmed)) {
      if (inList) { out.push("</" + inList + ">"); inList = null }
      out.push("<hr>")
      continue
    }

    // ---------- ordered list ----------
    const olMatch = trimmed.match(/^(\d+)\.\s+(.*)/)
    if (olMatch) {
      if (inList !== "ol") {
        if (inList) out.push("</" + inList + ">")
        out.push("<ol>")
        inList = "ol"
      }
      out.push("<li>" + inline(olMatch[2]) + "</li>")
      continue
    }

    // ---------- unordered list ----------
    const ulMatch = trimmed.match(/^[-*+]\s+(.*)/)
    if (ulMatch) {
      if (inList !== "ul") {
        if (inList) out.push("</" + inList + ">")
        out.push("<ul>")
        inList = "ul"
      }
      out.push("<li>" + inline(ulMatch[1]) + "</li>")
      continue
    }

    // ---------- paragraph ----------
    if (inList) { out.push("</" + inList + ">"); inList = null }
    out.push("<p>" + inline(raw) + "</p>")
  }

  if (inCodeBlock) out.push("</code></pre>")
  if (inList) out.push("</" + inList + ">")

  return out.join("\n")
}
</script>

<style scoped>
.markdown-body {
  line-height: 1.72;
  word-break: break-word;
}
</style>

<style>
/* Global (unscoped) styles for rendered markdown HTML */
.markdown-body p {
  margin: 0.36em 0;
}
.markdown-body strong {
  font-weight: 700;
}
.markdown-body em {
  font-style: italic;
}
.markdown-body code {
  color: #c4f5fb;
  background: rgba(103,232,249,0.08);
  border: 1px solid rgba(103,232,249,0.1);
  padding: 0.16em 0.42em;
  border-radius: 5px;
  font-size: 0.88em;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}
.markdown-body pre {
  color: #d7e2f2;
  background: #09101d;
  border: 1px solid rgba(148,163,184,.14);
  padding: 14px;
  border-radius: 10px;
  overflow-x: auto;
  margin: 0.5em 0;
  font-size: 0.85em;
  line-height: 1.4;
}
.markdown-body pre code {
  background: none;
  padding: 0;
  border-radius: 0;
  font-size: inherit;
}
.markdown-body ol,
.markdown-body ul {
  margin: 0.3em 0;
  padding-left: 1.5em;
}
.markdown-body li {
  margin: 0.15em 0;
}
.markdown-body a {
  color: #67e8f9;
  text-decoration: underline;
}
.markdown-body hr {
  border: none;
  border-top: 1px solid rgba(148,163,184,.2);
  margin: 0.6em 0;
}
.markdown-body h2 { font-size: 1.2em; margin: 0.5em 0 0.3em; }
.markdown-body h3 { font-size: 1.1em; margin: 0.4em 0 0.2em; }
.markdown-body h4 { font-size: 1.05em; margin: 0.3em 0 0.2em; }
</style>
