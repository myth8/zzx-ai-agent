<template>
  <div class="markdown-body" v-html="html"></div>
</template>

<script setup>
import { computed } from "vue"
import { renderSafeMarkdown } from "../utils/markdown.js"

const props = defineProps({
  content: { type: String, default: "" }
})

const html = computed(() => renderSafeMarkdown(props.content))
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
