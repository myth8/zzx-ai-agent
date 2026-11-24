<template>
  <main class="rag-page">
    <div class="rag-glow"></div>
    <header class="rag-nav">
      <button class="back-button" type="button" @click="router.push('/')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m15 18-6-6 6-6"/></svg>
        <span>工作台</span>
      </button>
      <div class="rag-brand"><span>R</span><b>RAG Knowledge Lab</b></div>
      <span class="admin-badge">ADMIN / 003</span>
    </header>

    <section class="rag-shell">
      <div class="rag-heading">
        <div>
          <span class="eyebrow">KNOWLEDGE OPERATIONS</span>
          <h1>知识库管理</h1>
          <p>维护 Agent 使用的 Markdown 知识源，并检查实际进入检索链路的文档切片。</p>
        </div>
        <div class="heading-actions">
          <input ref="fileInput" class="hidden-input" type="file" accept=".md,text/markdown" @change="handleFileChange">
          <button class="guide-button" type="button" :disabled="busy" @click="showFormatGuide = true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/></svg>
            格式示例
          </button>
          <button class="secondary-button" type="button" :disabled="busy" @click="handleRebuild">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 6v5h-5M4 18v-5h5"/><path d="M18.4 9A7 7 0 0 0 6.2 6.5L4 11M5.6 15A7 7 0 0 0 17.8 17.5L20 13"/></svg>
            检查并重建
          </button>
          <button class="primary-button" type="button" :disabled="busy" @click="openFilePicker">
            <span>+</span> 上传 Markdown
          </button>
        </div>
      </div>

      <div class="status-grid">
        <article><span>DOCUMENTS</span><strong>{{ stats.documentCount }}</strong><small>份知识文档</small></article>
        <article><span>CHUNKS</span><strong>{{ stats.chunkCount }}</strong><small>个检索切片</small></article>
        <article><span>INDEX</span><strong class="status-word" :class="indexState"><i></i>{{ indexWord }}</strong><small>{{ statusText }}</small></article>
      </div>

      <p v-if="message.text" class="page-message" :class="message.type">{{ message.text }}</p>

      <section v-if="uploadProgress.visible" class="upload-progress" :class="uploadProgress.phase">
        <div class="progress-copy">
          <div>
            <span>{{ uploadProgress.phase === 'complete' ? 'UPLOAD COMPLETE' : 'DOCUMENT PIPELINE' }}</span>
            <h3>{{ uploadProgress.title }}</h3>
            <p>{{ uploadProgress.detail }}</p>
          </div>
          <div class="progress-time">
            <strong v-if="!uploadProgress.indeterminate">{{ uploadProgress.percent }}%</strong>
            <strong v-else>处理中</strong>
            <small>{{ uploadProgress.elapsed }} 秒</small>
          </div>
        </div>
        <div class="progress-track" :class="{ indeterminate: uploadProgress.indeterminate }">
          <i :style="{ width: uploadProgress.percent + '%' }"></i>
        </div>
        <div class="progress-steps">
          <span v-for="(step, index) in uploadSteps" :key="step" :class="stepClass(index)"><i>{{ index + 1 }}</i>{{ step }}</span>
        </div>
      </section>

      <div class="manager-grid">
        <aside class="document-panel">
          <div class="panel-title">
            <div><span>DOCUMENT SOURCE</span><h2>文档目录</h2></div>
            <span>{{ documents.length }}</span>
          </div>

          <div v-if="loadingList" class="panel-state"><i></i>正在读取文档</div>
          <div v-else-if="documents.length" class="document-list">
            <button
              v-for="document in documents"
              :key="document.id"
              type="button"
              class="document-item"
              :class="{ active: selectedId === document.id }"
              @click="selectDocument(document.id)"
            >
              <span class="file-icon">MD</span>
              <span class="file-copy">
                <b>{{ document.display_name }}</b>
                <small>{{ document.filename }}</small>
                <em>{{ formatBytes(document.file_size) }} · {{ document.chunk_count }} 个切片</em>
              </span>
              <i class="status-dot" :class="document.status"></i>
            </button>
          </div>
          <div v-else class="empty-list">
            <span>∅</span>
            <h3>知识库还是空的</h3>
            <p>上传第一份 Markdown 文档开始构建检索索引。</p>
          </div>
        </aside>

        <section class="viewer-panel">
          <template v-if="selectedDocument">
            <header class="viewer-head">
              <div class="viewer-title">
                <span class="large-file-icon">MD</span>
                <div>
                  <span>KNOWLEDGE DOCUMENT</span>
                  <h2>{{ selectedDocument.display_name }}</h2>
                  <p>{{ selectedDocument.filename }} · {{ formatDate(selectedDocument.updated_at) }}</p>
                </div>
              </div>
              <button class="delete-button" type="button" :disabled="busy" @click="handleDelete">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/></svg>
                删除
              </button>
            </header>

            <div class="viewer-tabs">
              <button type="button" :class="{ active: activeTab === 'content' }" @click="activeTab = 'content'">查看全文</button>
              <button type="button" :class="{ active: activeTab === 'chunks' }" @click="showChunks">切片详情 <span>{{ selectedDocument.chunk_count }}</span></button>
            </div>

            <div class="viewer-body">
              <div v-if="loadingDetail" class="viewer-loading"><i></i><span>正在加载文档</span></div>
              <article v-else-if="activeTab === 'content'" class="markdown-document">
                <section v-if="documentMetadataEntries.length" class="document-metadata">
                  <div class="metadata-heading">
                    <div><span>DOCUMENT METADATA</span><h3>文档元数据</h3></div>
                    <small>独立于正文与切片保存</small>
                  </div>
                  <dl>
                    <div v-for="item in documentMetadataEntries" :key="item.key">
                      <dt>{{ metadataLabel(item.key) }}</dt>
                      <dd>{{ formatMetadataValue(item.value) }}</dd>
                    </div>
                  </dl>
                </section>
                <MarkdownRenderer :content="documentContent" />
              </article>
              <div v-else class="chunks-view">
                <div v-if="loadingChunks" class="viewer-loading"><i></i><span>正在生成切片预览</span></div>
                <template v-else>
                  <article v-for="chunk in chunks" :key="chunk.chunk_id || chunk.id" class="chunk-card">
                    <header>
                      <span>CHUNK {{ String(chunk.index).padStart(2, '0') }}</span>
                      <span>{{ chunk.char_count }} 字符</span>
                    </header>
                    <div class="chunk-meta">
                      <span v-for="(value, key) in chunkMetadata(chunk.metadata)" :key="key">{{ metadataLabel(key) }}: {{ formatMetadataValue(value) }}</span>
                    </div>
                    <details class="chunk-metadata-panel">
                      <summary>
                        <span><i>METADATA</i>全部切片元信息</span>
                        <small>{{ chunkMetadataEntries(chunk.metadata).length }} 个字段</small>
                      </summary>
                      <dl>
                        <div v-for="item in chunkMetadataEntries(chunk.metadata)" :key="item.key">
                          <dt>
                            <span>{{ metadataLabel(item.key) }}</span>
                            <small>{{ item.key }}</small>
                          </dt>
                          <dd>{{ formatMetadataValue(item.value) }}</dd>
                          <em :class="`origin-${metadataOrigin(item.key).type}`">{{ metadataOrigin(item.key).label }}</em>
                        </div>
                      </dl>
                      <p>文档继承字段来自 Markdown 顶部的 YAML 元数据；其余字段由标题解析和切片建索引过程自动生成。</p>
                    </details>
                    <pre>{{ chunk.content }}</pre>
                  </article>
                </template>
                <div v-if="!loadingChunks && !chunks.length" class="viewer-loading"><span>当前文档没有生成切片</span></div>
              </div>
            </div>
          </template>
          <div v-else class="empty-viewer">
            <div class="empty-orbit"><span>R</span></div>
            <h2>选择一份知识文档</h2>
            <p>可以查看 Markdown 全文，以及标题切分和长度切分后的实际片段。</p>
          </div>
        </section>
      </div>
    </section>

    <div v-if="showFormatGuide" class="guide-backdrop" @click.self="showFormatGuide = false">
      <section class="guide-dialog" role="dialog" aria-modal="true" aria-labelledby="guide-title">
        <header>
          <div><span>MARKDOWN SPECIFICATION</span><h2 id="guide-title">知识文档格式</h2></div>
          <button type="button" aria-label="关闭" @click="showFormatGuide = false">×</button>
        </header>
        <div class="guide-content">
          <div class="guide-notes">
            <h3>上传前请确认</h3>
            <ol>
              <li>文件使用 UTF-8 编码，扩展名必须是 <code>.md</code>。</li>
              <li>顶部使用两行 <code>---</code> 包围 YAML 文档元数据。</li>
              <li>正文使用一个一级标题，每个独立问题使用二级标题。</li>
              <li>建议保留右侧示例中的全部元数据字段，列表项按 YAML 缩进。</li>
            </ol>
            <a class="download-example" :href="exampleUrl" download="示例.md">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 20h14"/></svg>
              下载 示例.md
            </a>
          </div>
          <div class="example-preview"><div><span>示例.md</span><small>可直接下载后修改</small></div><pre>{{ examplePreview }}</pre></div>
        </div>
      </section>
    </div>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useHead } from '@vueuse/head'
import { useRouter } from 'vue-router'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import {
  deleteRagDocument,
  getRagDocument,
  getRagDocumentChunks,
  getRagIndexStatus,
  listRagDocuments,
  rebuildRagIndex,
  uploadRagDocument
} from '../api'

useHead({ title: 'RAG 知识库管理 - ZZX AI Agent' })

const router = useRouter()
const fileInput = ref(null)
const documents = ref([])
const selectedId = ref(null)
const selectedDocument = ref(null)
const documentContent = ref('')
const chunks = ref([])
const activeTab = ref('content')
const loadingList = ref(true)
const loadingDetail = ref(false)
const loadingChunks = ref(false)
const busy = ref(false)
const showFormatGuide = ref(false)
const statusText = ref('正在检查索引状态')
const indexState = ref('checking')
const stats = reactive({ documentCount: 0, chunkCount: 0 })
const message = reactive({ text: '', type: 'success' })
const uploadSteps = ['校验文件', '上传文档', '构建索引', '刷新页面']
const uploadProgress = reactive({
  visible: false,
  phase: 'validating',
  step: 0,
  percent: 0,
  elapsed: 0,
  indeterminate: false,
  title: '',
  detail: ''
})
let uploadTimer = null
let uploadHideTimer = null
const exampleUrl = `${import.meta.env.BASE_URL}示例.md`
const examplePreview = `---
schema_version: 1
title: 恋爱常见问题 - 暧昧篇
description: 面向暧昧阶段用户的关系确认与沟通指南。
status: 暧昧中
relationship_stage: situationship
category: 情感解惑
topics:
  - 关系确认
  - 沟通表达
audience:
  - 处于暧昧关系中的用户
language: zh-CN
version: "1.0"
source_type: curated
---

# 暧昧篇：在不确定中看清关系

## 1. 对方主动聊天代表喜欢我吗？

> 关键词：主动联系、关系判断

这里填写完整的问题分析和建议。`
const documentMetadataEntries = computed(() =>
  Object.entries(selectedDocument.value?.document_metadata || {}).map(([key, value]) => ({ key, value }))
)
const indexWord = computed(() => {
  if (busy.value) return 'SYNCING'
  if (indexState.value === 'stale') return 'STALE'
  if (indexState.value === 'error') return 'UNKNOWN'
  if (indexState.value === 'checking') return 'CHECKING'
  return 'READY'
})

const metadataLabels = {
  schema_version: '结构版本',
  title: '标题',
  description: '简介',
  status: '关系状态',
  relationship_stage: '关系阶段',
  category: '分类',
  topics: '主题',
  audience: '适用人群',
  language: '语言',
  version: '内容版本',
  source_type: '来源类型',
  source: '源文件',
  document_title: '文档标题',
  section_title: '章节标题',
  chunk_index: '切片序号',
  char_count: '字符数',
  chunk_id: '切片 ID',
  content_sha256: '内容指纹'
}

const headingMetadataKeys = new Set(['document_title', 'section_title'])
const generatedMetadataKeys = new Set([
  'source',
  'chunk_index',
  'char_count',
  'chunk_id',
  'content_sha256'
])

function showMessage(text, type = 'success') {
  message.text = text
  message.type = type
  window.clearTimeout(showMessage.timer)
  showMessage.timer = window.setTimeout(() => { message.text = '' }, 4200)
}

function apiError(error, fallback) {
  if (error.response?.status === 403) {
    router.replace('/')
    return '当前账号没有管理员权限'
  }
  return error.response?.data?.message || fallback
}

async function loadDocuments(preferredId = selectedId.value) {
  loadingList.value = true
  try {
    const response = await listRagDocuments()
    const data = response.data || {}
    documents.value = data.documents || []
    stats.documentCount = data.document_count || 0
    stats.chunkCount = data.chunk_count || 0
    if (!documents.value.length) {
      selectedId.value = null
      selectedDocument.value = null
      documentContent.value = ''
      chunks.value = []
      return
    }
    const target = documents.value.find(item => item.id === preferredId) || documents.value[0]
    await selectDocument(target.id)
  } catch (error) {
    showMessage(apiError(error, '读取文档列表失败'), 'error')
  } finally {
    loadingList.value = false
  }
}

async function loadIndexStatus() {
  indexState.value = 'checking'
  statusText.value = '正在核对源文件、数据库与向量索引'
  try {
    const response = await getRagIndexStatus()
    const status = response.data || {}
    indexState.value = status.up_to_date ? 'ready' : 'stale'
    statusText.value = status.reason || (status.up_to_date ? '当前索引已经是最新' : '索引需要重建')
    return status
  } catch (error) {
    indexState.value = 'error'
    statusText.value = '索引状态检查失败'
    throw error
  }
}

async function selectDocument(documentId) {
  if (loadingDetail.value) return
  selectedId.value = documentId
  activeTab.value = 'content'
  chunks.value = []
  loadingDetail.value = true
  try {
    const response = await getRagDocument(documentId)
    selectedDocument.value = response.data
    documentContent.value = response.data?.content || ''
  } catch (error) {
    showMessage(apiError(error, '读取文档失败'), 'error')
  } finally {
    loadingDetail.value = false
  }
}

async function showChunks() {
  activeTab.value = 'chunks'
  if (chunks.value.length || !selectedId.value) return
  loadingChunks.value = true
  try {
    const response = await getRagDocumentChunks(selectedId.value)
    chunks.value = response.data?.chunks || []
  } catch (error) {
    showMessage(apiError(error, '读取切片失败'), 'error')
  } finally {
    loadingChunks.value = false
  }
}

function openFilePicker() {
  if (!busy.value) fileInput.value?.click()
}

function setUploadPhase(phase, step, percent, title, detail, indeterminate = false) {
  uploadProgress.phase = phase
  uploadProgress.step = step
  uploadProgress.percent = percent
  uploadProgress.title = title
  uploadProgress.detail = detail
  uploadProgress.indeterminate = indeterminate
}

function beginUploadProgress(file) {
  window.clearTimeout(uploadHideTimer)
  uploadProgress.visible = true
  uploadProgress.elapsed = 0
  setUploadPhase('validating', 0, 6, `正在检查 ${file.name}`, '确认文件类型、名称与基础格式', false)
  window.clearInterval(uploadTimer)
  uploadTimer = window.setInterval(() => { uploadProgress.elapsed += 1 }, 1000)
}

function finishUploadProgress(success) {
  window.clearInterval(uploadTimer)
  uploadTimer = null
  if (success) {
    setUploadPhase('complete', 4, 100, '文档已成功入库', '文档、切片与检索索引已同步完成', false)
  }
  uploadHideTimer = window.setTimeout(() => { uploadProgress.visible = false }, success ? 2200 : 6000)
}

function stepClass(index) {
  if (uploadProgress.phase === 'complete' || index < uploadProgress.step) return 'done'
  if (index === uploadProgress.step) return 'active'
  return ''
}

async function handleFileChange(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.md')) {
    showMessage('仅支持上传 .md 文件', 'error')
    return
  }
  beginUploadProgress(file)
  busy.value = true
  statusText.value = '正在上传文档'
  try {
    setUploadPhase('uploading', 1, 10, '正在上传文档', `${formatBytes(file.size)} · UTF-8 Markdown`, false)
    const response = await uploadRagDocument(file, progressEvent => {
      const ratio = progressEvent.total ? progressEvent.loaded / progressEvent.total : progressEvent.progress
      if (typeof ratio === 'number') {
        uploadProgress.percent = Math.min(40, 10 + Math.round(ratio * 30))
      }
      if (ratio >= 1) {
        statusText.value = '正在切片并构建向量索引'
        setUploadPhase('indexing', 2, 48, '正在构建检索索引', '服务器正在切片、生成向量并刷新 BM25，这一步可能需要一些时间', true)
      }
    })
    const documentId = response.data?.document?.id
    setUploadPhase('refreshing', 3, 94, '正在刷新文档列表', '索引已经就绪，正在读取最新文档和切片信息', false)
    showMessage(response.msg || '文档上传成功')
    await loadDocuments(documentId)
    await loadIndexStatus()
    finishUploadProgress(true)
  } catch (error) {
    setUploadPhase('error', uploadProgress.step, uploadProgress.percent, '文档处理失败', apiError(error, '请检查文档格式后重试'), false)
    finishUploadProgress(false)
    showMessage(apiError(error, '文档上传失败'), 'error')
  } finally {
    busy.value = false
    if (indexState.value === 'checking') statusText.value = '等待重新检查索引状态'
  }
}

async function handleDelete() {
  if (!selectedDocument.value || busy.value) return
  const confirmed = window.confirm(`确定删除“${selectedDocument.value.filename}”吗？删除后会立即重建 RAG 索引。`)
  if (!confirmed) return
  busy.value = true
  statusText.value = '正在删除并刷新索引'
  try {
    const response = await deleteRagDocument(selectedDocument.value.id)
    showMessage(response.msg || '文档已删除')
    selectedId.value = null
    await loadDocuments(null)
    await loadIndexStatus()
  } catch (error) {
    showMessage(apiError(error, '删除文档失败'), 'error')
  } finally {
    busy.value = false
    if (indexState.value === 'checking') statusText.value = '等待重新检查索引状态'
  }
}

async function handleRebuild() {
  if (busy.value) return
  busy.value = true
  indexState.value = 'checking'
  statusText.value = '正在检查索引是否需要重建'
  try {
    const current = await loadIndexStatus()
    if (current.up_to_date) {
      showMessage('当前索引已经是最新，无需重建')
      return
    }
    indexState.value = 'stale'
    statusText.value = `${current.reason}，正在重建索引`
    const response = await rebuildRagIndex()
    showMessage(response.msg || '索引重建完成')
    await loadDocuments()
    await loadIndexStatus()
  } catch (error) {
    indexState.value = 'error'
    statusText.value = '索引检查或重建失败'
    showMessage(apiError(error, '索引重建失败'), 'error')
  } finally {
    busy.value = false
  }
}

function formatBytes(value) {
  const bytes = Number(value || 0)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(value) {
  if (!value) return ''
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function metadataLabel(key) {
  return metadataLabels[key] || key
}

function formatMetadataValue(value) {
  if (Array.isArray(value)) return value.join('、')
  if (typeof value === 'string' && (value.startsWith('[') || value.startsWith('{'))) {
    try {
      return formatMetadataValue(JSON.parse(value))
    } catch {
      return value
    }
  }
  if (value && typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value ?? '')
}

function chunkMetadata(metadata = {}) {
  const chunkKeys = ['section_title', 'document_title', 'chunk_id', 'content_sha256']
  return Object.fromEntries(
    Object.entries(metadata).filter(([key]) => chunkKeys.includes(key))
  )
}

function chunkMetadataEntries(metadata = {}) {
  return Object.entries(metadata || {}).map(([key, value]) => ({ key, value }))
}

function metadataOrigin(key) {
  if (Object.prototype.hasOwnProperty.call(selectedDocument.value?.document_metadata || {}, key)) {
    return { type: 'document', label: '文档继承' }
  }
  if (headingMetadataKeys.has(key)) {
    return { type: 'heading', label: '标题提取' }
  }
  if (generatedMetadataKeys.has(key)) {
    return { type: 'generated', label: '切片生成' }
  }
  return { type: 'other', label: '其他' }
}

onMounted(() => Promise.allSettled([loadDocuments(), loadIndexStatus()]))
onBeforeUnmount(() => {
  window.clearInterval(uploadTimer)
  window.clearTimeout(uploadHideTimer)
})
</script>

<style scoped>
.rag-page { position: relative; min-height: 100vh; overflow: hidden; background: linear-gradient(rgba(52,211,153,.025) 1px, transparent 1px), linear-gradient(90deg, rgba(52,211,153,.025) 1px, transparent 1px), #070b16; background-size: 52px 52px; }
.rag-glow { position: absolute; width: 700px; height: 700px; top: -430px; right: 5%; border-radius: 50%; background: #34d399; opacity: .12; filter: blur(130px); pointer-events: none; }
.rag-nav { position: relative; z-index: 2; height: 76px; max-width: 1440px; margin: 0 auto; padding: 0 30px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; border-bottom: 1px solid var(--line); }
.back-button { justify-self: start; display: flex; align-items: center; gap: 8px; padding: 8px 10px; color: var(--muted); background: transparent; border: 0; border-radius: 9px; }
.back-button:hover { color: var(--text); background: rgba(255,255,255,.04); }.back-button svg { width: 18px; }
.rag-brand { display: flex; align-items: center; gap: 10px; font: 700 14px 'Manrope', sans-serif; }.rag-brand > span { width: 30px; height: 30px; display: grid; place-items: center; color: #07110e; background: var(--success); border-radius: 9px; font-weight: 900; }
.admin-badge { justify-self: end; color: var(--success); font-size: 10px; font-weight: 800; letter-spacing: .13em; }
.rag-shell { position: relative; z-index: 1; width: min(1380px, calc(100% - 48px)); margin: 0 auto; padding: 60px 0 90px; }
.rag-heading { display: flex; justify-content: space-between; align-items: flex-end; gap: 30px; }.eyebrow { color: var(--success); font-size: 10px; font-weight: 800; letter-spacing: .18em; }.rag-heading h1 { margin-top: 12px; font: 800 clamp(38px, 5vw, 62px)/1.05 'Manrope', sans-serif; letter-spacing: -.055em; }.rag-heading p { max-width: 650px; margin-top: 14px; color: var(--muted); line-height: 1.7; }
.heading-actions { display: flex; gap: 10px; }.hidden-input { display: none; }.primary-button, .secondary-button, .guide-button { height: 46px; display: flex; align-items: center; justify-content: center; gap: 8px; padding: 0 16px; border-radius: 11px; font-weight: 750; transition: .2s; }.primary-button { color: #06110d; background: var(--success); border: 0; }.primary-button span { font-size: 20px; font-weight: 400; }.secondary-button, .guide-button { color: #b5c4d8; background: rgba(15,23,42,.72); border: 1px solid var(--line); }.secondary-button svg, .guide-button svg { width: 17px; }.guide-button { color: #8edfc4; border-color: rgba(52,211,153,.18); }.primary-button:hover:not(:disabled), .secondary-button:hover:not(:disabled), .guide-button:hover:not(:disabled) { transform: translateY(-2px); filter: brightness(1.08); }.primary-button:disabled, .secondary-button:disabled, .guide-button:disabled, .delete-button:disabled { opacity: .45; cursor: wait; }
.status-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 42px 0 20px; }.status-grid article { min-height: 112px; padding: 18px 20px; display: flex; flex-direction: column; justify-content: center; background: rgba(15,23,42,.64); border: 1px solid var(--line); border-radius: 16px; }.status-grid article > span { color: #66738a; font-size: 9px; font-weight: 800; letter-spacing: .16em; }.status-grid strong { margin-top: 6px; font: 800 28px 'Manrope', sans-serif; }.status-grid small { margin-top: 2px; color: var(--muted); }.status-word { display: flex; align-items: center; gap: 9px; color: var(--success); font-size: 18px !important; }.status-word i, .status-dot { border-radius: 50%; background: var(--success); box-shadow: 0 0 10px var(--success); }.status-word i { width: 7px; height: 7px; }
.status-word.checking { color: #67e8f9; }.status-word.checking i { background: #67e8f9; box-shadow: 0 0 10px #67e8f9; animation: pulse 1s infinite alternate; }.status-word.stale { color: #fbbf24; }.status-word.stale i { background: #fbbf24; box-shadow: 0 0 10px #fbbf24; }.status-word.error { color: var(--danger); }.status-word.error i { background: var(--danger); box-shadow: 0 0 10px var(--danger); }
.page-message { margin: 0 0 18px; padding: 12px 15px; border-radius: 11px; font-size: 13px; }.page-message.success { color: #a7f3d0; background: rgba(52,211,153,.08); border: 1px solid rgba(52,211,153,.22); }.page-message.error { color: #fecdd3; background: rgba(251,113,133,.08); border: 1px solid rgba(251,113,133,.22); }
.upload-progress { margin: 0 0 18px; padding: 18px 20px 16px; background: rgba(10,18,32,.94); border: 1px solid rgba(52,211,153,.2); border-radius: 15px; box-shadow: 0 16px 50px rgba(0,0,0,.18); }.upload-progress.error { border-color: rgba(251,113,133,.28); }.progress-copy { display: flex; align-items: center; justify-content: space-between; gap: 20px; }.progress-copy > div:first-child > span { color: var(--success); font-size: 8px; font-weight: 800; letter-spacing: .16em; }.upload-progress.error .progress-copy > div:first-child > span { color: var(--danger); }.progress-copy h3 { margin-top: 4px; color: #e4ecf8; font-size: 14px; }.progress-copy p { margin-top: 3px; color: #68778e; font-size: 10px; }.progress-time { flex: 0 0 auto; text-align: right; }.progress-time strong { display: block; color: var(--success); font: 800 15px 'Manrope', sans-serif; }.upload-progress.error .progress-time strong { color: var(--danger); }.progress-time small { color: #536178; font-size: 9px; }.progress-track { height: 5px; margin-top: 14px; overflow: hidden; background: #111b2c; border-radius: 10px; }.progress-track i { display: block; height: 100%; background: linear-gradient(90deg, #34d399, #67e8f9); border-radius: inherit; transition: width .3s ease; }.progress-track.indeterminate i { width: 38% !important; animation: indexing-progress 1.3s ease-in-out infinite; }.upload-progress.error .progress-track i { background: var(--danger); }.progress-steps { display: grid; grid-template-columns: repeat(4, 1fr); margin-top: 12px; }.progress-steps span { display: flex; align-items: center; gap: 6px; color: #46546a; font-size: 9px; }.progress-steps i { width: 17px; height: 17px; display: grid; place-items: center; border: 1px solid #263248; border-radius: 50%; font-size: 8px; font-style: normal; }.progress-steps span.active { color: #b8c8da; }.progress-steps span.active i { color: #06110d; background: var(--success); border-color: var(--success); }.progress-steps span.done { color: #6fae9a; }.progress-steps span.done i { color: var(--success); border-color: rgba(52,211,153,.45); }
.manager-grid { min-height: 680px; display: grid; grid-template-columns: 340px minmax(0, 1fr); overflow: hidden; background: rgba(10,16,31,.82); border: 1px solid var(--line); border-radius: 22px; box-shadow: var(--shadow); }.document-panel { padding: 22px 14px; border-right: 1px solid var(--line); background: rgba(9,15,28,.72); }.panel-title { padding: 0 8px 18px; display: flex; align-items: center; justify-content: space-between; }.panel-title div > span, .viewer-title div > span { color: #617086; font-size: 9px; font-weight: 800; letter-spacing: .15em; }.panel-title h2 { margin-top: 4px; font: 750 20px 'Manrope', sans-serif; }.panel-title > span { min-width: 28px; height: 28px; display: grid; place-items: center; color: var(--success); background: rgba(52,211,153,.08); border-radius: 8px; font-size: 11px; font-weight: 800; }
.document-list { display: flex; flex-direction: column; gap: 7px; }.document-item { position: relative; width: 100%; min-height: 82px; padding: 12px; display: flex; align-items: center; gap: 11px; color: inherit; text-align: left; background: transparent; border: 1px solid transparent; border-radius: 13px; transition: .18s; }.document-item:hover { background: rgba(255,255,255,.025); }.document-item.active { background: rgba(52,211,153,.07); border-color: rgba(52,211,153,.2); }.file-icon { width: 40px; height: 44px; flex: 0 0 40px; display: grid; place-items: center; color: var(--success); background: rgba(52,211,153,.08); border: 1px solid rgba(52,211,153,.17); border-radius: 9px; font: 800 10px 'Manrope', sans-serif; }.file-copy { min-width: 0; display: flex; flex: 1; flex-direction: column; }.file-copy b, .file-copy small, .file-copy em { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.file-copy b { color: #e4ecf8; font-size: 13px; }.file-copy small { margin-top: 3px; color: #718098; font-size: 10px; }.file-copy em { margin-top: 6px; color: #536178; font-size: 9px; font-style: normal; }.status-dot { width: 5px; height: 5px; flex: 0 0 5px; }.status-dot.failed { background: var(--danger); box-shadow: 0 0 10px var(--danger); }.status-dot.indexing { background: #fbbf24; box-shadow: 0 0 10px #fbbf24; }
.panel-state, .empty-list { min-height: 300px; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 25px; color: var(--muted); text-align: center; }.panel-state { flex-direction: row; gap: 10px; }.panel-state i, .viewer-loading i { width: 8px; height: 8px; border-radius: 50%; background: var(--success); animation: pulse 1s infinite alternate; }.empty-list > span { color: #47566c; font-size: 34px; }.empty-list h3 { margin-top: 15px; color: #ccd6e5; }.empty-list p { margin-top: 8px; color: #637087; font-size: 12px; line-height: 1.6; }
.viewer-panel { min-width: 0; display: flex; flex-direction: column; }.viewer-head { min-height: 102px; padding: 20px 24px; display: flex; align-items: center; justify-content: space-between; gap: 18px; border-bottom: 1px solid var(--line); }.viewer-title { min-width: 0; display: flex; align-items: center; gap: 14px; }.large-file-icon { width: 48px; height: 52px; flex: 0 0 48px; display: grid; place-items: center; color: #07110e; background: var(--success); border-radius: 11px; font: 900 11px 'Manrope', sans-serif; }.viewer-title div { min-width: 0; }.viewer-title h2 { margin-top: 3px; overflow: hidden; font: 750 20px 'Manrope', sans-serif; text-overflow: ellipsis; white-space: nowrap; }.viewer-title p { margin-top: 4px; color: #637087; font-size: 10px; }.delete-button { height: 38px; display: flex; align-items: center; gap: 7px; padding: 0 12px; color: #fb9aaa; background: rgba(251,113,133,.06); border: 1px solid rgba(251,113,133,.16); border-radius: 9px; }.delete-button:hover:not(:disabled) { background: rgba(251,113,133,.12); }.delete-button svg { width: 16px; }
.viewer-tabs { height: 52px; display: flex; gap: 6px; align-items: end; padding: 0 24px; border-bottom: 1px solid var(--line); }.viewer-tabs button { height: 44px; padding: 0 12px; color: #6f7d94; background: transparent; border: 0; border-bottom: 2px solid transparent; font-weight: 650; }.viewer-tabs button.active { color: var(--success); border-bottom-color: var(--success); }.viewer-tabs span { margin-left: 5px; color: #617087; font-size: 10px; }
.viewer-body { height: 526px; overflow-y: auto; }.markdown-document { max-width: 900px; padding: 30px 44px 70px; color: #cdd7e5; }.document-metadata { margin-bottom: 30px; padding: 18px; background: rgba(52,211,153,.035); border: 1px solid rgba(52,211,153,.14); border-radius: 14px; }.metadata-heading { display: flex; align-items: end; justify-content: space-between; gap: 16px; padding-bottom: 13px; border-bottom: 1px solid var(--line); }.metadata-heading span { color: var(--success); font-size: 8px; font-weight: 800; letter-spacing: .15em; }.metadata-heading h3 { margin-top: 3px; color: #e4ecf8; font-size: 15px; }.metadata-heading small { color: #617087; font-size: 9px; }.document-metadata dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 11px 18px; margin-top: 15px; }.document-metadata dl > div { min-width: 0; }.document-metadata dt { color: #607087; font-size: 9px; }.document-metadata dd { margin-top: 3px; color: #aebdd0; font-size: 11px; line-height: 1.55; overflow-wrap: anywhere; }.markdown-document :deep(.markdown-body) { font-size: 14px; line-height: 1.85; }.markdown-document :deep(.markdown-body h2), .markdown-document :deep(.markdown-body h3), .markdown-document :deep(.markdown-body h4) { color: #f0f5fc; margin-top: 1.25em; }.chunks-view { padding: 24px; display: flex; flex-direction: column; gap: 14px; }.chunk-card { overflow: hidden; background: #090f1d; border: 1px solid var(--line); border-radius: 14px; }.chunk-card header { height: 42px; padding: 0 14px; display: flex; align-items: center; justify-content: space-between; color: #65738a; border-bottom: 1px solid var(--line); font-size: 9px; font-weight: 800; letter-spacing: .11em; }.chunk-meta { padding: 10px 14px 0; display: flex; flex-wrap: wrap; gap: 6px; }.chunk-meta span { max-width: 100%; padding: 5px 7px; overflow: hidden; color: #8ca0b8; background: rgba(52,211,153,.055); border-radius: 6px; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }.chunk-metadata-panel { margin: 12px 14px 0; overflow: hidden; background: rgba(15,23,42,.5); border: 1px solid rgba(52,211,153,.12); border-radius: 10px; }.chunk-metadata-panel summary { min-height: 42px; padding: 9px 12px; display: flex; align-items: center; justify-content: space-between; gap: 14px; color: #a8b8cb; cursor: pointer; list-style: none; }.chunk-metadata-panel summary::-webkit-details-marker { display: none; }.chunk-metadata-panel summary > span { display: flex; align-items: center; gap: 9px; font-size: 11px; font-weight: 700; }.chunk-metadata-panel summary i { color: var(--success); font-size: 7px; font-style: normal; letter-spacing: .13em; }.chunk-metadata-panel summary small { color: #5f6e83; font-size: 9px; }.chunk-metadata-panel summary::after { content: '+'; color: #66778e; font-size: 17px; }.chunk-metadata-panel[open] summary::after { content: '−'; }.chunk-metadata-panel[open] summary { border-bottom: 1px solid var(--line); }.chunk-metadata-panel dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; background: var(--line); }.chunk-metadata-panel dl > div { position: relative; min-width: 0; padding: 12px; background: #0a1120; }.chunk-metadata-panel dt { display: flex; align-items: baseline; gap: 7px; }.chunk-metadata-panel dt span { color: #a9b9cd; font-size: 10px; font-weight: 700; }.chunk-metadata-panel dt small { color: #4f6077; font: 8px 'SFMono-Regular', Consolas, monospace; }.chunk-metadata-panel dd { margin: 7px 0 22px; color: #ced8e6; font: 10px/1.6 'SFMono-Regular', Consolas, monospace; overflow-wrap: anywhere; white-space: pre-wrap; }.chunk-metadata-panel em { position: absolute; bottom: 10px; left: 12px; padding: 2px 5px; border-radius: 4px; font-size: 7px; font-style: normal; }.chunk-metadata-panel .origin-document { color: #8bdcc1; background: rgba(52,211,153,.08); }.chunk-metadata-panel .origin-heading { color: #8dcfec; background: rgba(103,232,249,.08); }.chunk-metadata-panel .origin-generated { color: #c5b5f4; background: rgba(167,139,250,.09); }.chunk-metadata-panel .origin-other { color: #9aa8ba; background: rgba(148,163,184,.08); }.chunk-metadata-panel > p { padding: 10px 12px; color: #596a80; border-top: 1px solid var(--line); font-size: 9px; line-height: 1.6; }.chunk-card pre { padding: 14px; overflow: auto; color: #bdcadb; font: 12px/1.75 'SFMono-Regular', Consolas, monospace; white-space: pre-wrap; word-break: break-word; }.viewer-loading, .empty-viewer { min-height: 430px; display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--muted); }.empty-viewer { flex-direction: column; text-align: center; }.empty-orbit { width: 92px; height: 92px; display: grid; place-items: center; margin-bottom: 16px; border: 1px solid rgba(52,211,153,.25); border-radius: 50%; box-shadow: 0 0 60px rgba(52,211,153,.08); }.empty-orbit span { width: 48px; height: 48px; display: grid; place-items: center; color: #07110e; background: var(--success); border-radius: 14px; font-weight: 900; }.empty-viewer h2 { font: 750 22px 'Manrope', sans-serif; }.empty-viewer p { max-width: 440px; color: var(--muted); line-height: 1.7; }
@keyframes pulse { to { opacity: .3; transform: scale(.75); } }
@keyframes indexing-progress { 0% { transform: translateX(-120%); } 100% { transform: translateX(300%); } }
.guide-backdrop { position: fixed; z-index: 20; inset: 0; display: grid; place-items: center; padding: 24px; background: rgba(2,6,15,.82); backdrop-filter: blur(10px); }.guide-dialog { width: min(1040px, 100%); max-height: min(760px, calc(100vh - 48px)); overflow: hidden; background: #09101e; border: 1px solid rgba(52,211,153,.2); border-radius: 20px; box-shadow: 0 30px 100px rgba(0,0,0,.55); }.guide-dialog > header { height: 76px; padding: 0 24px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--line); }.guide-dialog > header span { color: var(--success); font-size: 8px; font-weight: 800; letter-spacing: .16em; }.guide-dialog > header h2 { margin-top: 3px; font-size: 20px; }.guide-dialog > header button { width: 34px; height: 34px; color: #78879c; background: rgba(255,255,255,.03); border: 1px solid var(--line); border-radius: 9px; font-size: 22px; }.guide-content { display: grid; grid-template-columns: 330px minmax(0, 1fr); max-height: calc(min(760px, 100vh - 48px) - 76px); }.guide-notes { padding: 26px; border-right: 1px solid var(--line); }.guide-notes h3 { color: #e1e9f5; font-size: 15px; }.guide-notes ol { margin: 18px 0 0 18px; color: #8695aa; font-size: 12px; line-height: 1.75; }.guide-notes li + li { margin-top: 9px; }.guide-notes code { padding: 2px 5px; color: #9fe8d0; background: rgba(52,211,153,.08); border-radius: 4px; }.download-example { height: 42px; margin-top: 24px; display: flex; align-items: center; justify-content: center; gap: 8px; color: #06110d; background: var(--success); border-radius: 10px; font-size: 12px; font-weight: 750; }.download-example svg { width: 16px; }.example-preview { min-width: 0; overflow: auto; background: #070c17; }.example-preview > div { position: sticky; top: 0; height: 42px; padding: 0 18px; display: flex; align-items: center; justify-content: space-between; background: #0c1423; border-bottom: 1px solid var(--line); }.example-preview > div span { color: #b8c6d9; font-size: 11px; font-weight: 700; }.example-preview > div small { color: #56647a; font-size: 9px; }.example-preview pre { padding: 20px; color: #9eb0c6; font: 11px/1.7 'SFMono-Regular', Consolas, monospace; white-space: pre-wrap; word-break: break-word; }
@media (max-width: 900px) { .rag-heading { align-items: flex-start; flex-direction: column; }.manager-grid { grid-template-columns: 1fr; }.document-panel { border-right: 0; border-bottom: 1px solid var(--line); }.document-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); }.viewer-body { height: auto; min-height: 520px; } }
@media (max-width: 720px) { .guide-content { grid-template-columns: 1fr; overflow-y: auto; }.guide-notes { border-right: 0; border-bottom: 1px solid var(--line); }.example-preview { min-height: 420px; }.progress-steps { grid-template-columns: repeat(2, 1fr); gap: 8px; } }
@media (max-width: 640px) { .rag-nav { grid-template-columns: 1fr auto; padding: 0 18px; }.rag-brand { display: none; }.rag-shell { width: min(100% - 28px, 1380px); padding-top: 42px; }.heading-actions { width: 100%; flex-direction: column-reverse; }.primary-button, .secondary-button, .guide-button { width: 100%; }.status-grid { grid-template-columns: 1fr; }.manager-grid { border-radius: 16px; }.viewer-head { align-items: flex-start; }.large-file-icon { display: none; }.markdown-document { padding: 26px 20px 50px; }.document-metadata dl, .chunk-metadata-panel dl { grid-template-columns: 1fr; }.metadata-heading small { display: none; }.chunks-view { padding: 14px; }.progress-copy p { max-width: 230px; }.guide-backdrop { padding: 12px; }.guide-dialog { max-height: calc(100vh - 24px); } }
</style>
