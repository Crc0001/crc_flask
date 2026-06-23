/**
 * MALDI-TOF 质谱匹配页面 JavaScript
 */

// 全局状态
let currentSpectrumFile = null;
let currentRefFile = null;
let latestMatchResults = [];

// DOM 元素
const uploadArea = document.getElementById('upload-area');
const spectrumFileInput = document.getElementById('spectrum-file');
const uploadPlaceholder = document.getElementById('upload-placeholder');
const fileInfo = document.getElementById('file-info');
const fileName = document.getElementById('file-name');
const fileSize = document.getElementById('file-size');
const btnRemoveFile = document.getElementById('btn-remove-file');
const btnMatch = document.getElementById('btn-match');
const resultsSection = document.getElementById('results-section');
const resultsList = document.getElementById('results-list');
const refStrainSelect = document.getElementById('ref-strain-select');
const refFileInput = document.getElementById('ref-file');
const btnAddRef = document.getElementById('btn-add-ref');
const referenceList = document.getElementById('reference-list');
const refCount = document.getElementById('ref-count');
const loadingOverlay = document.getElementById('loading-overlay');
const messageContainer = document.getElementById('message-container');


// 初始化
document.addEventListener('DOMContentLoaded', function() {
    initFileUpload();
    initButtons();
    loadStrainList();
    loadReferenceList();
});


/**
 * 显示消息
 */
function showMessage(message, type = 'info') {
    const messageBox = document.createElement('div');
    messageBox.className = `message-box message-${type}`;
    messageBox.textContent = message;
    messageContainer.appendChild(messageBox);

    // 3秒后自动消失
    setTimeout(() => {
        messageBox.remove();
    }, 3000);
}


/**
 * 显示/隐藏加载状态
 */
function setLoading(isLoading, text = '处理中...') {
    if (isLoading) {
        loadingOverlay.querySelector('.loading-text').textContent = text;
        loadingOverlay.style.display = 'flex';
    } else {
        loadingOverlay.style.display = 'none';
    }
}


/**
 * 初始化文件上传
 */
function initFileUpload() {
    // 点击上传区域
    uploadArea.addEventListener('click', () => {
        spectrumFileInput.click();
    });

    // 文件选择
    spectrumFileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            handleSpectrumFile(file);
        }
    });

    // 拖拽上传
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('drag-over');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('drag-over');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');

        const file = e.dataTransfer.files[0];
        if (file && file.name.endsWith('.txt')) {
            handleSpectrumFile(file);
        } else {
            showMessage('请上传 TXT 格式的文件', 'error');
        }
    });

    // 移除文件
    btnRemoveFile.addEventListener('click', (e) => {
        e.stopPropagation();
        clearSpectrumFile();
    });
}


/**
 * 处理上传的质谱文件
 */
function handleSpectrumFile(file) {
    currentSpectrumFile = file;

    // 显示文件信息
    uploadPlaceholder.style.display = 'none';
    fileInfo.style.display = 'flex';
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);

    // 启用匹配按钮
    btnMatch.disabled = false;

    // 隐藏之前的结果
    resultsSection.style.display = 'none';
}


/**
 * 清除质谱文件
 */
function clearSpectrumFile() {
    currentSpectrumFile = null;
    spectrumFileInput.value = '';

    uploadPlaceholder.style.display = 'block';
    fileInfo.style.display = 'none';
    btnMatch.disabled = true;
    resultsSection.style.display = 'none';
}


/**
 * 初始化按钮事件
 */
function initButtons() {
    // 匹配按钮
    btnMatch.addEventListener('click', startMatching);

    // 添加参考谱按钮
    btnAddRef.addEventListener('click', addReference);

    // 参考谱文件选择
    refFileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            currentRefFile = file;
            btnAddRef.disabled = !refStrainSelect.value;
        }
    });

    // 菌种选择变化
    refStrainSelect.addEventListener('change', () => {
        btnAddRef.disabled = !currentRefFile || !refStrainSelect.value;
    });
}


/**
 * 开始匹配
 */
async function startMatching() {
    if (!currentSpectrumFile) {
        showMessage('请先上传质谱文件', 'error');
        return;
    }

    const topK = parseInt(document.getElementById('param-topk').value) || 3;
    const tolerance = parseFloat(document.getElementById('param-tolerance').value) || 0.5;

    const formData = new FormData();
    formData.append('file', currentSpectrumFile);
    formData.append('top_k', topK);
    formData.append('mz_tolerance', tolerance);

    setLoading(true, '正在匹配...');

    try {
        const response = await fetch('/api/maldi/match', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            latestMatchResults = data.candidates;
            displayMatchResults(data.candidates, data.query_info, data.comparison_plot);
            showMessage('匹配完成', 'success');
        } else {
            showMessage(data.message || '匹配失败', 'error');
            resultsSection.style.display = 'none';
        }

    } catch (error) {
        console.error('匹配失败:', error);
        showMessage('匹配失败: ' + error.message, 'error');
        resultsSection.style.display = 'none';
    } finally {
        setLoading(false);
    }
}


/**
 * 显示匹配结果
 */
function displayMatchResults(candidates, queryInfo, comparisonPlot) {
    if (!candidates || candidates.length === 0) {
        resultsSection.style.display = 'none';
        return;
    }

    // 添加查询信息
    let html = '';

    if (queryInfo && queryInfo.sample_id) {
        html += `<div class="query-info">样本ID: ${escapeHtml(queryInfo.sample_id)} | 峰数量: ${queryInfo.peak_count}</div>`;
    }

    // 添加对比图
    if (comparisonPlot) {
        html += `
            <div class="comparison-plot-container">
                <div class="section-header">
                    <h5>质谱对比图（灰色：查询样本 | 红色：Top-1 参考谱）</h5>
                </div>
                <div class="comparison-plot">
                    <img src="data:image/png;base64,${comparisonPlot}" alt="质谱对比图">
                </div>
            </div>
        `;
    }

    // 添加候选列表
    candidates.forEach((candidate, index) => {
        const rank = index + 1;
        const score = (candidate.score * 100).toFixed(2);
        const cosineSim = (candidate.cosine_sim * 100).toFixed(2);
        const queryCov = (candidate.query_coverage * 100).toFixed(2);
        const refCov = (candidate.ref_coverage * 100).toFixed(2);

        html += `
            <div class="result-item" data-rank="${rank}">
                <div class="result-rank">${rank}</div>
                <div class="result-content">
                    <div class="result-strain">
                        <strong>${escapeHtml(candidate.strain_name || '未知')}</strong>
                        ${candidate.scientific_name ? `<span class="result-scientific">(${escapeHtml(candidate.scientific_name)})</span>` : ''}
                    </div>
                    <div class="result-score">综合分数: <span class="score-value">${score}%</span></div>
                    <div class="result-details">
                        <span>余弦相似度: ${cosineSim}%</span> |
                        <span>查询覆盖: ${queryCov}%</span> |
                        <span>参考覆盖: ${refCov}%</span> |
                        <span>匹配峰: ${candidate.matched_count}</span>
                    </div>
                    ${candidate.sample_id ? `<div class="result-sample">参考样本: ${escapeHtml(candidate.sample_id)}</div>` : ''}
                </div>
            </div>
        `;
    });

    resultsList.innerHTML = html;
    resultsSection.style.display = 'block';
}


/**
 * 加载菌种列表
 */
async function loadStrainList() {
    try {
        const response = await fetch('/api/maldi/strains');
        const data = await response.json();

        if (data.success) {
            refStrainSelect.innerHTML = '<option value="">请选择菌种</option>';

            data.strains.forEach(strain => {
                const option = document.createElement('option');
                option.value = strain.id;
                option.textContent = `${strain.name} ${strain.scientific_name ? `(${strain.scientific_name})` : ''}`;
                refStrainSelect.appendChild(option);
            });
        }

    } catch (error) {
        console.error('加载菌种列表失败:', error);
    }
}


/**
 * 加载参考谱列表
 */
async function loadReferenceList() {
    try {
        const response = await fetch('/api/maldi/reference/list');
        const data = await response.json();

        if (data.success) {
            displayReferenceList(data.references);
        }

    } catch (error) {
        console.error('加载参考谱列表失败:', error);
    }
}


/**
 * 显示参考谱列表
 */
function displayReferenceList(references) {
    refCount.textContent = references.length;

    if (references.length === 0) {
        referenceList.innerHTML = '<div class="empty-state"><p>暂无参考谱</p></div>';
        return;
    }

    let html = '';
    references.forEach(ref => {
        html += `
            <div class="reference-item">
                <div class="reference-info">
                    <div class="reference-strain"><strong>${escapeHtml(ref.strain_name || '未知')}</strong></div>
                    <div class="reference-meta">
                        <span>样本ID: ${escapeHtml(ref.sample_id || 'N/A')}</span> |
                        <span>峰数: ${ref.peak_count}</span>
                    </div>
                </div>
                <button type="button" class="btn-delete-ref" data-id="${ref.id}">删除</button>
            </div>
        `;
    });

    referenceList.innerHTML = html;

    // 绑定删除事件
    document.querySelectorAll('.btn-delete-ref').forEach(btn => {
        btn.addEventListener('click', () => {
            const refId = parseInt(btn.dataset.id);
            deleteReference(refId);
        });
    });
}


/**
 * 添加参考谱
 */
async function addReference() {
    const strainId = refStrainSelect.value;
    const file = refFileInput.files[0];

    if (!strainId || !file) {
        showMessage('请选择菌种和上传质谱文件', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('strain_id', strainId);

    setLoading(true, '正在添加...');

    try {
        const response = await fetch('/api/maldi/reference/add', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            showMessage('参考谱添加成功', 'success');

            // 清空表单
            refFileInput.value = '';
            currentRefFile = null;
            btnAddRef.disabled = true;

            // 重新加载列表
            loadReferenceList();
        } else {
            showMessage(data.message || '添加失败', 'error');
        }

    } catch (error) {
        console.error('添加参考谱失败:', error);
        showMessage('添加失败: ' + error.message, 'error');
    } finally {
        setLoading(false);
    }
}


/**
 * 删除参考谱
 */
async function deleteReference(refId) {
    if (!confirm('确定要删除这个参考谱吗？')) {
        return;
    }

    setLoading(true, '正在删除...');

    try {
        const response = await fetch(`/api/maldi/reference/${refId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            showMessage('删除成功', 'success');
            loadReferenceList();
        } else {
            showMessage(data.message || '删除失败', 'error');
        }

    } catch (error) {
        console.error('删除参考谱失败:', error);
        showMessage('删除失败: ' + error.message, 'error');
    } finally {
        setLoading(false);
    }
}


/**
 * 格式化文件大小
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}


/**
 * HTML 转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
