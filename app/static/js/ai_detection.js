let latestDetectionSummary = '';
let latestSelectedStrainName = '';
let latestOrbCandidates = [];
let latestMaldiFile = null;

document.addEventListener('DOMContentLoaded', function() {
    // 初始化三级下拉框
    initLocationDropdowns();

    // 初始化表单验证
    initFormValidation();

    // 初始化检测按钮
    initDetectionButtons();

    // 初始化MALDI-TOF质谱图上传功能
    initMaldiUpload();

    // 初始化16S RNA匹配功能
    init16sMatching();

    // 初始化报告按钮与弹窗
    initReportActions();

    // 初始化全局事件
    initGlobalEvents();

    // 显示欢迎消息
    showWelcomeMessage();

    // 确保结果区域初始状态正确
    resetResultArea();
});

// ===== 三级下拉框功能 =====
function initLocationDropdowns() {
    const classGeneralSelect = document.getElementById('class_general');
    const classLevelOneSelect = document.getElementById('class_levelone');
    const classLevelTwoSelect = document.getElementById('class_leveltwo');
    const fullLocationInput = document.getElementById('full_location');
    const locationContainer = document.querySelector('.location-dropdown-container');

    if (!classGeneralSelect) return;

    // 从后端接口获取分类数据，避免模板内联JS导致编辑器报错
    fetchLocationData(classGeneralSelect, classLevelOneSelect, classLevelTwoSelect, fullLocationInput, null, locationContainer);
}

function populateGeneralDropdown(select, hierarchy) {
    select.innerHTML = '<option value="">请选择大类</option>';
    Object.keys(hierarchy).sort().forEach(general => {
        const option = document.createElement('option');
        option.value = general;
        option.textContent = general;
        select.appendChild(option);
    });
}

function bindDropdownEvents(generalSelect, levelOneSelect, levelTwoSelect, fullLocationInput, hierarchy, locationContainer) {
    // 第0级变化时，更新第一级
    generalSelect.addEventListener('change', function() {
        const selectedGeneral = this.value;

        // 清空并禁用下级下拉框
        levelOneSelect.innerHTML = '<option value="">请选择一级分类</option>';
        levelTwoSelect.innerHTML = '<option value="">请选择二级分类</option>';
        levelOneSelect.disabled = !selectedGeneral;
        levelTwoSelect.disabled = true;
        updateFullLocation(generalSelect, levelOneSelect, levelTwoSelect, fullLocationInput);

        // 更新容器样式
        updateLocationContainerStyle(locationContainer, generalSelect, levelOneSelect, levelTwoSelect);

        if (selectedGeneral && hierarchy[selectedGeneral]) {
            // 启用第一级下拉框
            levelOneSelect.disabled = false;

            // 填充第一级选项
            Object.keys(hierarchy[selectedGeneral]).sort().forEach(levelOne => {
                const option = document.createElement('option');
                option.value = levelOne;
                option.textContent = levelOne;
                levelOneSelect.appendChild(option);
            });
        }
    });

    // 第一级变化时，更新第二级
    levelOneSelect.addEventListener('change', function() {
        const selectedGeneral = generalSelect.value;
        const selectedLevelOne = this.value;

        // 清空第二级
        levelTwoSelect.innerHTML = '<option value="">请选择二级分类</option>';
        levelTwoSelect.disabled = !selectedLevelOne;
        updateFullLocation(generalSelect, levelOneSelect, levelTwoSelect, fullLocationInput);

        // 更新容器样式
        updateLocationContainerStyle(locationContainer, generalSelect, levelOneSelect, levelTwoSelect);

        if (selectedGeneral && selectedLevelOne &&
            hierarchy[selectedGeneral] &&
            hierarchy[selectedGeneral][selectedLevelOne]) {

            // 启用第二级下拉框
            levelTwoSelect.disabled = false;

            // 填充第二级选项
            hierarchy[selectedGeneral][selectedLevelOne].sort().forEach(levelTwo => {
                const option = document.createElement('option');
                option.value = levelTwo;
                option.textContent = levelTwo;
                levelTwoSelect.appendChild(option);
            });
        }
    });

    // 第二级变化时，更新完整地址
    levelTwoSelect.addEventListener('change', function() {
        updateFullLocation(generalSelect, levelOneSelect, levelTwoSelect, fullLocationInput);
        updateLocationContainerStyle(locationContainer, generalSelect, levelOneSelect, levelTwoSelect);
    });

    // 初始样式
    updateLocationContainerStyle(locationContainer, generalSelect, levelOneSelect, levelTwoSelect);
}

function updateLocationContainerStyle(container, generalSelect, levelOneSelect, levelTwoSelect) {
    if (!container) return;

    // 如果所有下拉框都有值，显示成功样式
    if (generalSelect.value && levelOneSelect.value && levelTwoSelect.value) {
        container.style.borderColor = '#28a745';
        container.style.backgroundColor = '#f0fff4';
    } else if (generalSelect.value || levelOneSelect.value) {
        // 如果有部分值，显示警告样式
        container.style.borderColor = '#ffc107';
        container.style.backgroundColor = '#fffbf0';
    } else {
        // 如果没有值，重置样式
        container.style.borderColor = '';
        container.style.backgroundColor = '';
    }
}

function updateFullLocation(generalSelect, levelOneSelect, levelTwoSelect, fullLocationInput) {
    const general = generalSelect.value;
    const levelOne = levelOneSelect.value;
    const levelTwo = levelTwoSelect.value;

    let fullLocation = '';
    if (general && levelOne && levelTwo) {
        fullLocation = `${general}/${levelOne}/${levelTwo}`;
    } else if (general && levelOne) {
        fullLocation = `${general}/${levelOne}`;
    } else if (general) {
        fullLocation = general;
    }

    fullLocationInput.value = fullLocation;
}

function fetchLocationData(generalSelect, levelOneSelect, levelTwoSelect, fullLocationInput, hierarchy, locationContainer) {
    fetch('/api/location_data')
        .then(response => {
            if (!response.ok) throw new Error('网络响应不正常');
            return response.json();
        })
        .then(data => {
            window.locationHierarchy = data;
            populateGeneralDropdown(generalSelect, data);
            bindDropdownEvents(generalSelect, levelOneSelect, levelTwoSelect, fullLocationInput, data, locationContainer);
        })
        .catch(error => {
            console.error('获取分类数据失败:', error);
            showDataError();
        });
}

function showDataError() {
    const locationGroup = document.querySelector('.location-group');
    if (!locationGroup) return;

    const errorDiv = document.createElement('div');
    errorDiv.className = 'location-error';
    errorDiv.style.cssText = `
        color: #dc3545;
        font-size: 12px;
        margin-top: 5px;
    `;
    errorDiv.textContent = '加载分类数据失败，请刷新页面重试';
    locationGroup.appendChild(errorDiv);
}

// ===== 表单验证功能 =====
function initFormValidation() {
    const form = document.getElementById('detectionForm');
    if (!form) return;

    // 文件选择反馈 + 即时图片预览
    const fileInput = document.getElementById('image-input');
    if (fileInput) {
        fileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                showFileInfo(this, '已选择: ');
                previewSelectedImage(this.files[0]);
            }
        });
    }
}

// ===== MALDI-TOF质谱图上传功能 =====
function initMaldiUpload() {
    const maldiInput = document.getElementById('maldi-txt-input');
    const maldiBtn = document.getElementById('maldi-generate-btn');

    if (!maldiInput || !maldiBtn) return;

    // 设置MALDI按钮的事件
    maldiBtn.removeEventListener('click', handleMaldiGenerate);
    maldiBtn.addEventListener('click', handleMaldiGenerate);

    // 监听文件选择变化
    maldiInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (!file) return;

        // 检查文件类型
        const fileName = file.name.toLowerCase();
        const isTxt = fileName.endsWith('.txt');

        if (!isTxt) {
            showError('请上传 TXT 格式文件');
            maldiInput.value = '';
            return;
        }

        latestMaldiFile = file;

        // 重置结果区域
        resetMaldiResultArea();

        // 重置按钮文字
        maldiBtn.textContent = '生成质谱图';
    });
}

function resetMaldiResultArea() {
    const resultPlaceholder = document.getElementById('maldi-result-placeholder');
    const matchResults = document.getElementById('maldi-match-results');
    const chartPlaceholder = document.getElementById('maldi-chart-placeholder');

    if (resultPlaceholder && matchResults) {
        resultPlaceholder.style.display = 'flex';
        matchResults.style.display = 'none';
        matchResults.innerHTML = '';
    }

    if (chartPlaceholder) {
        chartPlaceholder.innerHTML = `
            <div class="chart-icon">📈</div>
            <div class="chart-info">
                <h4>质谱分析图</h4>
                <p>请上传 TXT 文件并生成质谱图</p>
                <p style="font-size: 12px; margin-top: 5px;">支持：TXT 格式</p>
            </div>
        `;
    }
}

// 处理MALDI质谱图生成和匹配
function handleMaldiGenerate() {
    const maldiInput = document.getElementById('maldi-txt-input');
    const maldiBtn = document.getElementById('maldi-generate-btn');
    const chartPlaceholder = document.getElementById('maldi-chart-placeholder');
    const resultPlaceholder = document.getElementById('maldi-result-placeholder');
    const matchResults = document.getElementById('maldi-match-results');

    const file = (maldiInput && maldiInput.files && maldiInput.files[0]) || latestMaldiFile;

    if (!file) {
        showError('请先上传 TXT 文件');
        return;
    }

    const isTxt = file.name.toLowerCase().endsWith('.txt');

    if (!isTxt) {
        showError('请上传 TXT 格式文件');
        return;
    }

    // 显示加载状态
    setButtonState(maldiBtn, true, '生成中...');
    chartPlaceholder.innerHTML = '<div class="loading-spinner"></div><p>正在生成质谱图...</p>';
    resultPlaceholder.innerHTML = '<div class="loading-spinner"></div><p>正在匹配菌种...</p>';

    // 创建FormData
    const formData = new FormData();
    formData.append('file', file);

    // 调用匹配API
    fetch('/api/maldi/match', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        console.log('MALDI匹配响应:', data);
        if (data.success) {
            // 显示质谱图
            if (data.comparison_plot) {
                const img = document.createElement('img');
                img.src = 'data:image/png;base64,' + data.comparison_plot;
                img.alt = 'MALDI质谱对比图';
                img.style.width = '100%';
                img.style.height = '100%';
                img.style.objectFit = 'contain';
                img.style.borderRadius = 'var(--radius-sm)';
                chartPlaceholder.innerHTML = '';
                chartPlaceholder.appendChild(img);
            } else {
                console.warn('没有返回质谱图');
            }

            // 显示匹配结果
            displayMaldiMatchResults(data.candidates);

            setButtonState(maldiBtn, false, '重新生成');
        } else {
            showError(data.message || '匹配失败');
            resetMaldiResultArea();
            setButtonState(maldiBtn, false, '生成质谱图');
        }
    })
    .catch(error => {
        console.error('MALDI匹配错误:', error);
        showError('匹配失败: ' + error.message);
        resetMaldiResultArea();
        setButtonState(maldiBtn, false, '生成质谱图');
    });
}

function displayMaldiMatchResults(candidates) {
    const resultPlaceholder = document.getElementById('maldi-result-placeholder');
    const matchResults = document.getElementById('maldi-match-results');

    if (!candidates || candidates.length === 0) {
        resultPlaceholder.style.display = 'flex';
        resultPlaceholder.innerHTML = `
            <div class="result-icon">❌</div>
            <div class="result-info-text">
                <h4>未找到匹配结果</h4>
                <p>数据库中没有匹配的菌种</p>
            </div>
        `;
        matchResults.style.display = 'none';
        return;
    }

    // 隐藏占位符，显示结果
    resultPlaceholder.style.display = 'none';
    matchResults.style.display = 'block';

    // 构建Excel表格HTML
    let html = `
        <table class="maldi-results-table">
            <thead>
                <tr>
                    <th>序号</th>
                    <th>菌株中文名称</th>
                    <th>菌株英文名称</th>
                    <th>综合得分</th>
                    <th>余弦相似度</th>
                    <th>查询覆盖率</th>
                    <th>参考覆盖率</th>
                    <th>匹配峰数</th>
                </tr>
            </thead>
            <tbody>
    `;

    candidates.forEach((candidate, index) => {
        const rank = index + 1;
        const score = (candidate.score * 100).toFixed(2);
        const cosineSim = (candidate.cosine_sim * 100).toFixed(2);
        const queryCov = (candidate.query_coverage * 100).toFixed(2);
        const refCov = (candidate.ref_coverage * 100).toFixed(2);

        html += `
            <tr class="${rank === 1 ? 'top-match-row' : ''}">
                <td>${rank}</td>
                <td>${candidate.strain_name || '未知菌种'}</td>
                <td>${candidate.scientific_name || '-'}</td>
                <td class="score-cell">${score}%</td>
                <td>${cosineSim}%</td>
                <td>${queryCov}%</td>
                <td>${refCov}%</td>
                <td>${candidate.matched_count}</td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
    `;

    matchResults.innerHTML = html;
}

// ===== 16S RNA匹配功能 =====
function init16sMatching() {
    const rnaInput = document.getElementById('rna-sequence-input');
    const matchBtn = document.getElementById('rna-match-btn');
    const clearBtn = document.getElementById('rna-clear-btn');

    if (!rnaInput || !matchBtn || !clearBtn) return;

    // 匹配按钮
    matchBtn.addEventListener('click', handle16sMatch);

    // 清空按钮
    clearBtn.addEventListener('click', function() {
        rnaInput.value = '';
        reset16sResultArea();
    });

    // 输入变化时重置结果
    rnaInput.addEventListener('input', function() {
        if (!this.value.trim()) {
            reset16sResultArea();
        }
    });
}

function reset16sResultArea() {
    const resultPlaceholder = document.getElementById('rna-result-placeholder');
    const matchResults = document.getElementById('rna-match-results');

    if (resultPlaceholder && matchResults) {
        resultPlaceholder.style.display = 'flex';
        matchResults.style.display = 'none';
        matchResults.innerHTML = '';
    }
}

function handle16sMatch() {
    const rnaInput = document.getElementById('rna-sequence-input');
    const matchBtn = document.getElementById('rna-match-btn');
    const resultPlaceholder = document.getElementById('rna-result-placeholder');

    const sequence = rnaInput.value.trim();

    if (!sequence) {
        showError('请输入 16S RNA 序列');
        return;
    }

    // 显示加载状态
    setButtonState(matchBtn, true, '匹配中...');
    resultPlaceholder.innerHTML = '<div class="loading-spinner"></div><p>正在匹配菌种...</p>';

    // 创建FormData
    const formData = new FormData();
    formData.append('sequence', sequence);
    formData.append('top_k', '5');

    // 调用匹配API
    fetch('/api/16s/match', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        console.log('16S匹配响应:', data);
        if (data.success) {
            // 显示匹配结果
            display16sMatchResults(data.candidates, data.query_info);
            setButtonState(matchBtn, false, '匹配');
        } else {
            showError(data.message || '匹配失败');
            reset16sResultArea();
            setButtonState(matchBtn, false, '匹配');
        }
    })
    .catch(error => {
        console.error('16S匹配错误:', error);
        showError('匹配失败: ' + error.message);
        reset16sResultArea();
        setButtonState(matchBtn, false, '匹配');
    });
}

function display16sMatchResults(candidates, queryInfo) {
    const resultPlaceholder = document.getElementById('rna-result-placeholder');
    const matchResults = document.getElementById('rna-match-results');

    if (!candidates || candidates.length === 0) {
        resultPlaceholder.style.display = 'flex';
        resultPlaceholder.innerHTML = `
            <div class="result-icon">❌</div>
            <div class="result-info-text">
                <h4>未找到匹配结果</h4>
                <p>数据库中没有匹配的菌种</p>
            </div>
        `;
        matchResults.style.display = 'none';
        return;
    }

    // 隐藏占位符，显示结果
    resultPlaceholder.style.display = 'none';
    matchResults.style.display = 'block';

    // 构建Excel表格HTML
    let html = `
        <div class="rna-query-info">
            <strong>查询序列：</strong>${queryInfo.preview} (长度: ${queryInfo.length} bp)
        </div>
        <table class="rna-results-table">
            <thead>
                <tr>
                    <th>序号</th>
                    <th>菌株中文名称</th>
                    <th>菌株英文名称</th>
                    <th>相似度</th>
                    <th>匹配长度</th>
                    <th>查询长度</th>
                    <th>参考长度</th>
                </tr>
            </thead>
            <tbody>
    `;

    candidates.forEach((candidate, index) => {
        const rank = index + 1;
        const similarity = (candidate.similarity * 100).toFixed(2);

        html += `
            <tr class="${rank === 1 ? 'top-match-row' : ''}">
                <td>${rank}</td>
                <td>${candidate.strain_name || '未知菌种'}</td>
                <td>${candidate.scientific_name || '-'}</td>
                <td class="score-cell">${similarity}%</td>
                <td>${candidate.match_length}</td>
                <td>${candidate.query_length}</td>
                <td>${candidate.ref_length}</td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
    `;

    matchResults.innerHTML = html;
}

// ===== 检测按钮功能 =====
function initDetectionButtons() {
    const detectBtn = document.getElementById('orb-detect-btn');
    const resultBox = document.getElementById('orb-result');

    if (!detectBtn || !resultBox) return;

    detectBtn.addEventListener('click', function() {
        const imageInput = document.getElementById('image-input');
        const imageFile = imageInput && imageInput.files ? imageInput.files[0] : null;

        if (!imageFile) {
            showError('请先在“选择文件”中上传图片');
            return;
        }

        resultBox.innerHTML = '<div style="text-align:center; padding:30px;">🔍 ORB智能检测中...</div>';
        setButtonState(detectBtn, true, '检测中...');

        const formData = new FormData();
        formData.append('image', imageFile);

        fetch('/api/orb_detect', {
            method: 'POST',
            body: formData
        })
            .then(response => response.json())
            .then(data => {
                if (!data.success) {
                    throw new Error(data.message || '智能检测失败');
                }

                const candidates = Array.isArray(data.candidates) ? data.candidates : [];
                if (candidates.length === 0) {
                    throw new Error('未返回候选菌种');
                }

                latestOrbCandidates = candidates;
                latestDetectionSummary = data.analysis_text || '已完成 ORB 智能检测。';
                latestSelectedStrainName = data.recommended_strain_name || candidates[0].strain_name || '';

                resultBox.innerHTML = renderOrbCandidates(candidates, latestSelectedStrainName);
                bindCandidateSelection();

                showSuccess('智能检测完成，请选择可信菌种');
            })
            .catch(error => {
                const msg = error.message || '智能检测失败';
                showError(msg);
                resultBox.innerHTML = `<div style="text-align:center; padding:24px; color:#6b7280;">${escapeHtml(msg)}</div>`;
                latestOrbCandidates = [];
                latestDetectionSummary = '';
                latestSelectedStrainName = '';
            })
            .finally(() => {
                setButtonState(detectBtn, false, '检测');
            });
    });
}

function renderOrbCandidates(candidates, selectedName) {
    const rows = candidates.map((item, idx) => {
        const strainName = item.strain_name || `候选${idx + 1}`;
        const checked = strainName === selectedName ? 'checked' : '';
        const score = Number(item.score || 0) * 100;
        const orbScore = Number(item.orb_score || 0) * 100;
        const colorScore = Number(item.color_score || 0) * 100;

        return `
            <label class="orb-candidate-item ${checked ? 'selected' : ''}" data-strain-name="${escapeHtml(strainName)}">
                <div class="orb-candidate-main">
                    <input type="radio" name="orb-candidate" value="${escapeHtml(strainName)}" ${checked}>
                    <div class="orb-candidate-text">
                        <div class="orb-candidate-name">${escapeHtml(strainName)}</div>
                        <div class="orb-candidate-sub">综合分 ${score.toFixed(2)}%</div>
                    </div>
                </div>
                <div class="orb-candidate-metrics">ORB ${orbScore.toFixed(2)}% / 颜色 ${colorScore.toFixed(2)}%</div>
            </label>
        `;
    }).join('');

    return `
        <div class="orb-result-wrap">
            <div class="orb-result-title">候选菌种（Top ${candidates.length}）</div>
            <div class="orb-candidate-list">${rows}</div>
            <div class="orb-result-note">当前选择：<strong>${escapeHtml(selectedName || '')}</strong></div>
        </div>
    `;
}

function bindCandidateSelection() {
    const radios = document.querySelectorAll('input[name="orb-candidate"]');
    radios.forEach(radio => {
        radio.addEventListener('change', function() {
            latestSelectedStrainName = this.value || '';

            const allItems = document.querySelectorAll('.orb-candidate-item');
            allItems.forEach(el => {
                if (el.getAttribute('data-strain-name') === latestSelectedStrainName) {
                    el.classList.add('selected');
                } else {
                    el.classList.remove('selected');
                }
            });

            const note = document.querySelector('.orb-result-note strong');
            if (note) {
                note.textContent = latestSelectedStrainName;
            }
        });
    });
}

function escapeHtml(text) {
    return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// ===== 全局事件处理 =====
function initReportActions() {
    const viewBtn = document.getElementById('view-report-btn');
    const closeBtn = document.getElementById('close-report-btn');
    const saveBtn = document.getElementById('save-report-btn');
    const exportPdfBtn = document.getElementById('export-report-pdf-btn');
    const modal = document.getElementById('report-modal');
    const reportContent = document.getElementById('report-content');

    if (!viewBtn || !modal || !reportContent) return;

    viewBtn.addEventListener('click', function() {
        const imageInput = document.getElementById('image-input');
        const maldiInput = document.getElementById('maldi-input');
        const sampleCode = document.getElementById('sample-code');
        const collectDate = document.getElementById('collect-date');
        const fullLocation = document.getElementById('full_location');

        const imageFile = imageInput && imageInput.files ? imageInput.files[0] : null;
        const maldiFile = (maldiInput && maldiInput.files && maldiInput.files[0]) || latestMaldiFile;

        if (!imageFile) {
            showError('请先上传样本图片');
            return;
        }

        if (!latestSelectedStrainName) {
            showError('请先完成智能检测，并选择可信菌种');
            return;
        }

        const imageUrl = URL.createObjectURL(imageFile);
        const maldiUrl = maldiFile ? URL.createObjectURL(maldiFile) : '';

        reportContent.innerHTML = `
            <div class="report-item">
                <div class="report-item-label">样品编号（可编辑）</div>
                <input class="report-edit-input" id="report-field-sample-code" type="text" value="${(sampleCode && sampleCode.value.trim()) || ''}" placeholder="请输入样品编号">
            </div>
            <div class="report-item">
                <div class="report-item-label">采集日期（可编辑）</div>
                <input class="report-edit-input" id="report-field-collect-date" type="date" value="${(collectDate && collectDate.value) || ''}">
            </div>
            <div class="report-item report-item-full">
                <div class="report-item-label">来源（可编辑）</div>
                <input class="report-edit-input" id="report-field-source-location" type="text" value="${(fullLocation && fullLocation.value.trim()) || ''}" placeholder="例如：食品/乳制品/发酵乳">
            </div>
            <div class="report-item report-item-full">
                <div class="report-item-label">菌种名称（可编辑）</div>
                <input class="report-edit-input" id="report-field-strain-name" type="text" value="${latestSelectedStrainName}" placeholder="请输入菌种名称">
            </div>
            <div class="report-item report-item-full">
                <div class="report-item-label">智能检测结论（可编辑）</div>
                <textarea class="report-edit-textarea" id="report-field-llm-result" placeholder="请输入或修改分析结论">${latestDetectionSummary || ''}</textarea>
            </div>
            <div class="report-item">
                <div class="report-item-label">样本图片</div>
                <img class="report-thumb" src="${imageUrl}" alt="样本图片">
            </div>
            <div class="report-item">
                <div class="report-item-label">MALDI-TOF图谱</div>
                ${maldiUrl ? `<img class="report-thumb" src="${maldiUrl}" alt="MALDI图谱">` : '<div class="report-item-value">未上传</div>'}
            </div>
        `;

        modal.style.display = 'flex';
    });

    if (closeBtn) {
        closeBtn.addEventListener('click', function() {
            modal.style.display = 'none';
        });
    }

    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });

    if (saveBtn) {
        saveBtn.addEventListener('click', function() {
            const imageInput = document.getElementById('image-input');
            const maldiInput = document.getElementById('maldi-input');
            const sampleCode = document.getElementById('sample-code');
            const collectDate = document.getElementById('collect-date');
            const fullLocation = document.getElementById('full_location');

            const imageFile = imageInput && imageInput.files ? imageInput.files[0] : null;
            if (!imageFile) {
                showError('请先上传样本图片');
                return;
            }

            const sampleCodeInput = document.getElementById('report-field-sample-code');
            const collectDateInput = document.getElementById('report-field-collect-date');
            const sourceLocationInput = document.getElementById('report-field-source-location');
            const strainNameInput = document.getElementById('report-field-strain-name');
            const llmResultInput = document.getElementById('report-field-llm-result');

            const editedSampleCode = (sampleCodeInput && sampleCodeInput.value.trim()) || '';
            const editedCollectDate = (collectDateInput && collectDateInput.value) || '';
            const editedSourceLocation = (sourceLocationInput && sourceLocationInput.value.trim()) || '';
            const editedStrainName = (strainNameInput && strainNameInput.value.trim()) || '';
            const editedLlmResult = (llmResultInput && llmResultInput.value.trim()) || '';

            if (!editedStrainName) {
                showError('请填写菌种名称');
                return;
            }

            const formData = new FormData();
            formData.append('sample_code', editedSampleCode);
            formData.append('collect_date', editedCollectDate);
            formData.append('source_location', editedSourceLocation);
            formData.append('strain_name', editedStrainName);
            formData.append('llm_result', editedLlmResult);
            formData.append('image', imageFile);

            const maldiFile = (maldiInput && maldiInput.files && maldiInput.files[0]) || latestMaldiFile;
            if (maldiFile) {
                formData.append('maldi_image', maldiFile);
            }

            setButtonState(saveBtn, true, '录入中...');
            fetch('/api/save_detection_report', {
                method: 'POST',
                body: formData
            })
                .then(response => response.json())
                .then(data => {
                    if (!data.success) {
                        throw new Error(data.message || '录入失败');
                    }
                    showSuccess('报告已录入菌种数据库');
                    latestSelectedStrainName = editedStrainName;
                    latestDetectionSummary = editedLlmResult;
                    modal.style.display = 'none';
                })
                .catch(error => {
                    showError(error.message || '录入失败');
                })
                .finally(() => {
                    setButtonState(saveBtn, false, '录入菌种数据库');
                });
        });
    }

    if (exportPdfBtn) {
        exportPdfBtn.addEventListener('click', function() {
            const imageInput = document.getElementById('image-input');
            const maldiInput = document.getElementById('maldi-input');

            const imageFile = imageInput && imageInput.files ? imageInput.files[0] : null;
            if (!imageFile) {
                showError('请先上传样本图片');
                return;
            }

            const sampleCodeInput = document.getElementById('report-field-sample-code');
            const collectDateInput = document.getElementById('report-field-collect-date');
            const sourceLocationInput = document.getElementById('report-field-source-location');
            const strainNameInput = document.getElementById('report-field-strain-name');
            const llmResultInput = document.getElementById('report-field-llm-result');

            const editedSampleCode = (sampleCodeInput && sampleCodeInput.value.trim()) || '';
            const editedCollectDate = (collectDateInput && collectDateInput.value) || '';
            const editedSourceLocation = (sourceLocationInput && sourceLocationInput.value.trim()) || '';
            const editedStrainName = (strainNameInput && strainNameInput.value.trim()) || '';
            const editedLlmResult = (llmResultInput && llmResultInput.value.trim()) || '';

            const formData = new FormData();
            formData.append('sample_code', editedSampleCode);
            formData.append('collect_date', editedCollectDate);
            formData.append('source_location', editedSourceLocation);
            formData.append('strain_name', editedStrainName);
            formData.append('llm_result', editedLlmResult);
            formData.append('image', imageFile);

            const maldiFile = (maldiInput && maldiInput.files && maldiInput.files[0]) || latestMaldiFile;
            if (maldiFile) {
                formData.append('maldi_image', maldiFile);
            }

            setButtonState(exportPdfBtn, true, '导出中...');
            fetch('/api/export_detection_report_pdf', {
                method: 'POST',
                body: formData
            })
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(data => {
                            throw new Error((data && data.message) || '导出PDF失败');
                        });
                    }
                    return response.blob();
                })
                .then(async blob => {
                    const downloadName = editedSampleCode
                        ? `菌种检测报告_${editedSampleCode}.pdf`
                        : '菌种检测报告.pdf';

                    if (window.showSaveFilePicker && window.isSecureContext) {
                        try {
                            const handle = await window.showSaveFilePicker({
                                suggestedName: downloadName,
                                types: [
                                    {
                                        description: 'PDF 文件',
                                        accept: { 'application/pdf': ['.pdf'] }
                                    }
                                ]
                            });
                            const writable = await handle.createWritable();
                            await writable.write(blob);
                            await writable.close();
                            showSuccess('PDF导出成功');
                            return;
                        } catch (pickerError) {
                            if (pickerError && pickerError.name === 'AbortError') {
                                return;
                            }
                        }
                    }

                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(blob);
                    link.download = downloadName;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    URL.revokeObjectURL(link.href);
                    showSuccess('PDF导出成功');
                })
                .catch(error => {
                    showError(error.message || '导出PDF失败');
                })
                .finally(() => {
                    setButtonState(exportPdfBtn, false, '导出PDF');
                });
        });
    }
}

function initGlobalEvents() {
    // 回车键提交支持
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type !== 'file') {
            e.preventDefault();
            const form = e.target.closest('form');
            if (form && form.id === 'detectionForm') {
                const detectBtn = form.querySelector('.detect-btn');
                if (detectBtn) {
                    detectBtn.click();
                }
            }
        }
    });

    // 页面卸载提示
    window.addEventListener('beforeunload', function(e) {
        const detectBtn = document.querySelector('.detect-btn');
        if (detectBtn && detectBtn.disabled) {
            e.preventDefault();
            e.returnValue = '检测正在进行中，确定要离开此页面吗？';
        }
    });
}

// ===== 工具函数 =====
function showError(message) {
    // 移除现有的错误提示
    const existingToast = document.querySelector('.error-toast');
    if (existingToast) existingToast.remove();

    // 创建新的错误提示
    const toast = document.createElement('div');
    toast.className = 'error-toast';
    toast.innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 18px;">⚠️</span>
            <span>${message}</span>
        </div>
    `;

    // 添加样式
    Object.assign(toast.style, {
        position: 'fixed',
        top: '20px',
        right: '20px',
        background: '#dc3545',
        color: 'white',
        padding: '15px 20px',
        borderRadius: '6px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        zIndex: '9999',
        animation: 'slideIn 0.3s ease-out',
        maxWidth: '300px',
        wordWrap: 'break-word'
    });

    document.body.appendChild(toast);

    // 3秒后自动移除
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 300);
    }, 3000);
}

function showSuccess(message) {
    // 移除现有的成功提示
    const existingToast = document.querySelector('.success-toast');
    if (existingToast) existingToast.remove();

    // 创建新的成功提示
    const toast = document.createElement('div');
    toast.className = 'success-toast';
    toast.innerHTML = `
        <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 18px;">✅</span>
            <span>${message}</span>
        </div>
    `;

    // 添加样式
    Object.assign(toast.style, {
        position: 'fixed',
        top: '20px',
        right: '20px',
        background: '#28a745',
        color: 'white',
        padding: '15px 20px',
        borderRadius: '6px',
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        zIndex: '9999',
        animation: 'slideIn 0.3s ease-out',
        maxWidth: '300px',
        wordWrap: 'break-word'
    });

    document.body.appendChild(toast);

    // 3秒后自动移除
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease-out';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 300);
    }, 3000);
}

function setButtonState(button, isLoading, text) {
    if (!button) return;
    button.disabled = isLoading;
    button.innerHTML = text || button.innerHTML;
    button.style.opacity = isLoading ? '0.7' : '1';
    button.style.cursor = isLoading ? 'not-allowed' : 'pointer';
}

function showFileInfo(input, prefix) {
    if (!input.files || input.files.length === 0) return;

    const fileName = input.files[0].name;
    const parent = input.parentNode;

    // 查找或创建文件信息显示区域
    let infoDiv = parent.querySelector('.file-info');
    if (!infoDiv) {
        infoDiv = document.createElement('div');
        infoDiv.className = 'file-info';
        parent.appendChild(infoDiv);
    }

    infoDiv.textContent = `${prefix}${fileName}`;
}

function previewSelectedImage(file) {
    const imageContent = document.querySelector('.image-preview-card .image-content');
    if (!imageContent || !file) return;

    const imageUrl = URL.createObjectURL(file);
    imageContent.innerHTML = `
        <div class="image-container">
            <img src="${imageUrl}" alt="样本图片" id="sample-image">
        </div>
    `;
}

function showWelcomeMessage() {
    setTimeout(() => {
        const messages = [
            "欢迎使用菌种鉴定系统！",
            "请填写样本信息并上传图片进行检测",
            "系统支持多种检测方式，请按需使用"
        ];
        const randomMsg = messages[Math.floor(Math.random() * messages.length)];
        console.log(`%c${randomMsg}`, 'color: #2c7be5; font-size: 14px; font-weight: bold;');
    }, 1000);
}