// 趋势分析图表功能
document.addEventListener('DOMContentLoaded', function() {
    // 全局变量
    let mainChart = null;
    let currentChartType = document.getElementById('type').value;

    // 统一 HTML 转义：后端/数据库文本插入 innerHTML 前必须经过它
    // （菌种名、采样地点等来自用户录入，是潜在的 XSS 数据源）
    function escapeHtml(text) {
        if (text === null || text === undefined) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // 初始化
    initPage();

    // 页面初始化
    function initPage() {
        setupEventListeners();
        loadInitialData();
    }

    // 设置事件监听器
    function setupEventListeners() {
        // 表单提交
        const analysisForm = document.getElementById('analysis-form');
        if (analysisForm) {
            analysisForm.addEventListener('submit', function(e) {
                e.preventDefault();
                loadChartData();
            });
        }

        // 统计类型下拉框变化时自动重新加载
        const typeSelect = document.getElementById('type');
        if (typeSelect) {
            typeSelect.addEventListener('change', function() {
                currentChartType = this.value;
                updateChartTitle();
                loadChartData();
            });
        }

        // 时间粒度下拉框变化时自动重新加载
        const granularitySelect = document.getElementById('granularity');
        if (granularitySelect) {
            granularitySelect.addEventListener('change', loadChartData);
        }

        // 窗口大小变化时重绘图表
        let resizeTimer;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function() {
                if (mainChart) {
                    mainChart.resize();
                }
            }, 250);
        });
    }

    // 更新图表标题
    function updateChartTitle() {
        const chartTitle = document.getElementById('chart-title');
        const statType = document.getElementById('stat-type');

        if (currentChartType === 'strain') {
            chartTitle.textContent = '菌种出现次数趋势分析';
            statType.textContent = '菌种出现次数';
        } else {
            chartTitle.textContent = '采样地点分布分析';
            statType.textContent = '采样地点';
        }
    }

    // 加载初始数据
    function loadInitialData() {
        loadChartData();
    }

    // 加载图表数据
    function loadChartData() {
        // 显示加载状态
        showLoading(true);

        // 获取表单数据
        const form = document.getElementById('analysis-form');
        if (!form) {
            showLoading(false);
            return;
        }

        const formData = new FormData(form);
        const params = new URLSearchParams(formData).toString();

        // 更新UI显示
        updateUIInfo(formData);

        // 请求数据
        fetch(`/analysis/data?${params}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP错误! 状态: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // 检查是否有错误
                if (data.error) {
                    throw new Error(data.error);
                }
                renderChart(data);
                updateStatistics(data);
                updateLegend(data);
            })
            .catch(error => {
                console.error('获取数据失败:', error);
                showError('获取数据失败，请检查数据库连接或筛选条件');
            })
            .finally(() => {
                showLoading(false);
            });
    }

    // 更新UI信息
    function updateUIInfo(formData) {
        const startDate = formData.get('start_date');
        const endDate = formData.get('end_date');
        const granularity = formData.get('granularity');

        // 更新时间范围显示
        const timeRangeText = document.getElementById('time-range-text');
        if (timeRangeText) {
            timeRangeText.textContent = `${startDate} 至 ${endDate}`;
        }

        const statDateRange = document.getElementById('stat-date-range');
        if (statDateRange) {
            statDateRange.textContent = `${startDate} 至 ${endDate}`;
        }

        // 更新时间粒度显示
        let granularityText = '按天';
        if (granularity === 'week') granularityText = '按周';
        else if (granularity === 'month') granularityText = '按月';

        const statGranularity = document.getElementById('stat-granularity');
        if (statGranularity) {
            statGranularity.textContent = granularityText;
        }
    }

    // 显示/隐藏加载状态
    function showLoading(show) {
        const loadingOverlay = document.getElementById('chart-loading');
        if (loadingOverlay) {
            loadingOverlay.style.display = show ? 'flex' : 'none';
        }
    }

    // 渲染图表 - 关键修复：防止图表高度无限增长
    function renderChart(data) {
        const canvas = document.getElementById('main-chart');
        if (!canvas) return;

        // 获取容器尺寸，设置canvas固定尺寸
        const container = canvas.parentElement;
        const containerWidth = container.clientWidth;
        const containerHeight = container.clientHeight;

        // 设置canvas固定尺寸
        canvas.width = containerWidth;
        canvas.height = containerHeight;

        const ctx = canvas.getContext('2d');

        // 销毁旧图表
        if (mainChart) {
            mainChart.destroy();
        }

        // 检查是否有数据
        if (!data.datasets || data.datasets.length === 0) {
            renderEmptyChart(ctx, '暂无数据');
            resetStatistics();
            updateLegend(null);
            return;
        }

        // 生成颜色
        const colors = generateColors(data.datasets.length);

        // 准备数据集
        const datasets = data.datasets.map((dataset, index) => {
            const color = colors[index];

            return {
                label: dataset.label,
                data: dataset.data,
                backgroundColor: color.background,
                borderColor: color.border,
                borderWidth: 1,
                borderRadius: 4,
                hoverBackgroundColor: color.hover,
                hoverBorderWidth: 2,
                // 关键配置：使柱状图紧挨且不留空隙
                barPercentage: 0.9,
                categoryPercentage: 0.8,
            };
        });

        // 图表配置 - 关键修复：设置固定尺寸和响应式
        const config = {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(255, 255, 255, 0.95)',
                        titleColor: '#2c3e50',
                        bodyColor: '#34495e',
                        borderColor: '#e1e8ed',
                        borderWidth: 1,
                        cornerRadius: 8,
                        padding: 12,
                        displayColors: true,
                        boxPadding: 5,
                        callbacks: {
                            label: function(context) {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y;
                                const unit = currentChartType === 'strain' ? '次' : '个';
                                return `${label}: ${value}${unit}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            display: false,
                            drawBorder: false
                        },
                        ticks: {
                            color: '#7f8c8d',
                            maxRotation: 45,
                            minRotation: 0,
                            font: {
                                size: 12
                            }
                        },
                        title: {
                            display: true,
                            text: '时间',
                            color: '#2c3e50',
                            font: {
                                weight: 'bold',
                                size: 13
                            }
                        },
                        // 关键配置：确保柱状图紧挨中间不留空
                        offset: true,
                        barPercentage: 0.9,
                        categoryPercentage: 0.8
                    },
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)',
                            drawBorder: false
                        },
                        ticks: {
                            color: '#7f8c8d',
                            precision: 0,
                            font: {
                                size: 12
                            },
                            callback: function(value) {
                                return value;
                            }
                        },
                        title: {
                            display: true,
                            text: currentChartType === 'strain' ? '出现次数' : '样本数量',
                            color: '#2c3e50',
                            font: {
                                weight: 'bold',
                                size: 13
                            }
                        }
                    }
                },
                animation: {
                    duration: 500,
                    easing: 'easeOutQuart'
                }
            }
        };

        // 创建图表
        mainChart = new Chart(ctx, config);

        // 强制重绘，确保尺寸正确
        setTimeout(() => {
            if (mainChart) {
                mainChart.resize();
            }
        }, 100);
    }

    // 渲染空图表
    function renderEmptyChart(ctx, message = '暂无数据') {
        mainChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: []
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        enabled: false
                    }
                }
            }
        });

        // 在画布上显示提示信息
        ctx.save();
        ctx.font = '14px Arial';
        ctx.fillStyle = '#95a5a6';
        ctx.textAlign = 'center';
        ctx.fillText(message, ctx.canvas.width / 2, ctx.canvas.height / 2);
        ctx.restore();
    }

    // 生成颜色
    function generateColors(count) {
        const colors = [];
        const hueStep = 360 / Math.max(count, 1);

        for (let i = 0; i < count; i++) {
            const hue = (i * hueStep) % 360;
            const saturation = 70;
            const lightness = 60;

            colors.push({
                background: `hsla(${hue}, ${saturation}%, ${lightness}%, 0.8)`,
                border: `hsl(${hue}, ${saturation}%, ${lightness - 20}%)`,
                hover: `hsla(${hue}, ${saturation}%, ${lightness}%, 1)`
            });
        }

        return colors;
    }

    // 更新统计信息
    function updateStatistics(data) {
        if (!data || !data.labels || !data.datasets) {
            resetStatistics();
            return;
        }

        // 数据点数量
        const dataPoints = data.labels.length * data.datasets.length;

        const dataPointsCount = document.getElementById('data-points-count');
        if (dataPointsCount) {
            dataPointsCount.textContent = dataPoints.toLocaleString();
        }

        const statDataPoints = document.getElementById('stat-data-points');
        if (statDataPoints) {
            statDataPoints.textContent = dataPoints.toLocaleString();
        }

        // 数据系列数量
        const statDatasets = document.getElementById('stat-datasets');
        if (statDatasets) {
            statDatasets.textContent = data.datasets.length.toLocaleString();
        }

        // 计算总数
        let total = 0;
        data.datasets.forEach(dataset => {
            if (dataset.data && Array.isArray(dataset.data)) {
                total += dataset.data.reduce((sum, value) => sum + value, 0);
            }
        });

        const statTotal = document.getElementById('stat-total');
        if (statTotal) {
            statTotal.textContent = total.toLocaleString();
        }
    }

    // 重置统计信息
    function resetStatistics() {
        const dataPointsCount = document.getElementById('data-points-count');
        if (dataPointsCount) {
            dataPointsCount.textContent = '0';
        }

        const statDataPoints = document.getElementById('stat-data-points');
        if (statDataPoints) {
            statDataPoints.textContent = '0';
        }

        const statDatasets = document.getElementById('stat-datasets');
        if (statDatasets) {
            statDatasets.textContent = '0';
        }

        const statTotal = document.getElementById('stat-total');
        if (statTotal) {
            statTotal.textContent = '0';
        }
    }

    // 更新图例
    function updateLegend(data) {
        const legendContainer = document.getElementById('chart-legend');
        const legendCount = document.getElementById('legend-count');

        if (!data || !data.datasets || data.datasets.length === 0) {
            if (legendContainer) {
                legendContainer.innerHTML = `
                    <div class="empty-legend">
                        📊
                        <p>暂无数据</p>
                    </div>
                `;
            }
            if (legendCount) {
                legendCount.textContent = '0项';
            }
            return;
        }

        // 更新数量
        if (legendCount) {
            legendCount.textContent = `${data.datasets.length}项`;
        }

        // 生成颜色
        const colors = generateColors(data.datasets.length);

        // 生成图例HTML
        let legendHTML = '';

        data.datasets.forEach((dataset, index) => {
            const color = colors[index];
            const total = dataset.data ? dataset.data.reduce((sum, val) => sum + val, 0) : 0;
            const label = escapeHtml(dataset.label);

            legendHTML += `
                <div class="legend-item" style="border-left-color: ${color.border}">
                    <div class="legend-color" style="background-color: ${color.background}"></div>
                    <div class="legend-info">
                        <span class="legend-name" title="${label}">${label}</span>
                        <span class="legend-value">${total.toLocaleString()}${currentChartType === 'strain' ? '次' : '个'}</span>
                    </div>
                </div>
            `;
        });

        if (legendContainer) {
            legendContainer.innerHTML = legendHTML;
        }
    }

    // 显示错误信息
    function showError(message) {
        const chartContainer = document.querySelector('.chart-container');
        if (!chartContainer) return;

        // 移除旧的错误信息
        const oldError = chartContainer.querySelector('.error-message');
        if (oldError) oldError.remove();

        // 创建错误信息
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.innerHTML = `
            <i class="fas fa-exclamation-triangle" style="font-size: 1.5rem; margin-bottom: 8px;"></i>
            <p style="margin: 0; font-size: 0.9rem;">${message}</p>
        `;

        chartContainer.appendChild(errorDiv);

        // 5秒后移除
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.remove();
            }
        }, 5000);
    }
});