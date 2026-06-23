class StrainDatabase {
    constructor() {
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.bindPopState();
        this.createImageModal();
    }

    bindEvents() {
        // 搜索表单提交
        const searchForm = document.getElementById('search-form');
        if (searchForm) {
            searchForm.addEventListener('submit', (e) => this.handleSearch(e));
        }

        // 表格事件代理 - 使用更可靠的委托方式
        document.addEventListener('click', (e) => {
            this.handleTableClick(e);
        });

        // 编辑弹窗关闭
        const editModal = document.getElementById('edit-modal');
        if (editModal) {
            editModal.addEventListener('click', (e) => {
                if (e.target.classList.contains('close') || e.target.classList.contains('modal-mask')) {
                    this.closeModal();
                }
            });
        }
    }

    bindPopState() {
        window.addEventListener('popstate', () => {
            this.loadPage(window.location.href);
        });
    }

    async handleSearch(e) {
        e.preventDefault();
        const form = e.target;
        const formData = new FormData(form);
        const params = new URLSearchParams(formData);

        // 重置到第一页
        params.set('page', '1');

        await this.loadPage(`?${params.toString()}`);
    }

    handleTableClick(e) {
        const target = e.target;

        // 编辑按钮
        if (target.classList.contains('edit-btn')) {
            e.preventDefault();
            this.openEditModal(target.dataset.id);
        }

        // 删除按钮
        if (target.classList.contains('delete-btn')) {
            e.preventDefault();
            this.handleDelete(target.dataset.id);
        }

        // 质谱图点击放大
        if (target.classList.contains('mass-spectrum-thumbnail')) {
            e.preventDefault();
            const imgSrc = target.getAttribute('src') || target.getAttribute('data-src');
            if (imgSrc) {
                console.log('点击质谱图，图片地址:', imgSrc);
                this.openImageModal(imgSrc);
            }
        }

        // 分页链接
        if (target.classList.contains('pagination-btn') || target.classList.contains('pagination-page')) {
            if (target.href && !target.classList.contains('disabled')) {
                e.preventDefault();
                this.loadPage(target.href);
            }
        }
    }

    createImageModal() {
        // 如果已存在则先移除
        const existingModal = document.getElementById('image-modal');
        if (existingModal) {
            existingModal.remove();
        }

        // 创建图片模态框
        const modal = document.createElement('div');
        modal.id = 'image-modal';
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            cursor: pointer;
        `;

        const imgContainer = document.createElement('div');
        imgContainer.style.cssText = `
            position: relative;
            max-width: 90%;
            max-height: 90%;
            display: flex;
            align-items: center;
            justify-content: center;
        `;

        const img = document.createElement('img');
        img.id = 'full-size-image';
        img.style.cssText = `
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            border: 2px solid white;
            border-radius: 8px;
            background: white;
            padding: 5px;
        `;

        // 关闭按钮
        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '×';
        closeBtn.style.cssText = `
            position: absolute;
            top: -40px;
            right: -10px;
            background: rgba(0, 0, 0, 0.7);
            border: none;
            color: white;
            font-size: 30px;
            cursor: pointer;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        `;
        closeBtn.onclick = (e) => {
            e.stopPropagation();
            this.closeImageModal();
        };

        // 添加点击遮罩关闭
        modal.onclick = (e) => {
            if (e.target === modal) {
                this.closeImageModal();
            }
        };

        imgContainer.appendChild(img);
        imgContainer.appendChild(closeBtn);
        modal.appendChild(imgContainer);
        document.body.appendChild(modal);

        console.log('图片模态框已创建');
    }

    openImageModal(src) {
        const modal = document.getElementById('image-modal');
        const img = document.getElementById('full-size-image');

        if (!modal || !img) {
            console.error('未找到模态框或图片元素');
            // 重新创建模态框
            this.createImageModal();
            // 再次尝试打开
            setTimeout(() => this.openImageModal(src), 100);
            return;
        }

        console.log('打开图片模态框:', src);
        img.src = src;
        img.alt = '质谱图';
        modal.style.display = 'flex';

        // 防止页面滚动
        document.body.style.overflow = 'hidden';

        // ESC键关闭
        const escHandler = (e) => {
            if (e.key === 'Escape') {
                this.closeImageModal();
                document.removeEventListener('keydown', escHandler);
            }
        };
        document.addEventListener('keydown', escHandler);

        // 图片加载错误处理
        img.onerror = () => {
            console.error('图片加载失败:', src);
            img.alt = '图片加载失败，请检查图片地址';
            img.style.border = '2px dashed red';
            img.style.backgroundColor = '#ffe6e6';
        };

        img.onload = () => {
            console.log('图片加载成功');
        };
    }

    closeImageModal() {
        const modal = document.getElementById('image-modal');
        const img = document.getElementById('full-size-image');

        if (modal) {
            modal.style.display = 'none';
        }
        if (img) {
            img.src = '';
            img.alt = '';
        }

        // 恢复页面滚动
        document.body.style.overflow = 'auto';
    }

    async openEditModal(sampleId) {
        try {
            const response = await fetch(`/strain_db/edit/${sampleId}`);
            const html = await response.text();

            document.getElementById('modal-content').innerHTML = html;
            document.getElementById('edit-modal').style.display = 'flex';

            this.bindEditForm();
        } catch (error) {
            console.error('打开编辑弹窗失败:', error);
            alert('加载失败，请重试');
        }
    }

    bindEditForm() {
        const form = document.getElementById('edit-form');
        if (!form) return;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            try {
                const formData = new FormData(form);
                const response = await fetch(form.action, {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (result.success) {
                    this.showSuccessMessage(result.message);
                    this.updateRow(result.data);

                    // 2秒后关闭弹窗
                    setTimeout(() => this.closeModal(), 2000);
                } else {
                    alert(result.message || '保存失败');
                }
            } catch (error) {
                console.error('保存失败:', error);
                alert('保存失败，请检查网络');
            }
        });
    }

    async handleDelete(sampleId) {
        if (!confirm('确定要删除这条记录吗？此操作不可恢复！')) {
            return;
        }

        try {
            const response = await fetch(`/strain_db/delete/${sampleId}`, {
                method: 'POST'
            });

            const result = await response.json();

            if (result.success) {
                this.removeRow(result.id);
                // 重新加载当前页
                await this.loadPage(window.location.href);
            } else {
                alert(result.message || '删除失败');
            }
        } catch (error) {
            console.error('删除失败:', error);
            alert('删除失败，请检查网络');
        }
    }

    async loadPage(url) {
        try {
            // 显示加载状态
            const tableContainer = document.getElementById('table-container');
            if (tableContainer) {
                tableContainer.innerHTML = '<div style="padding: 20px; text-align: center; color: #999;">加载中...</div>';
            }

            const response = await fetch(url, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) throw new Error('请求失败');

            const html = await response.text();

            if (tableContainer) {
                tableContainer.innerHTML = html;
            }

            // 更新浏览器地址栏
            window.history.pushState({}, '', url);
        } catch (error) {
            console.error('加载页面失败:', error);
            alert('加载失败，请刷新页面重试');
        }
    }

    closeModal() {
        const modal = document.getElementById('edit-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    showSuccessMessage(message) {
        const modalBody = document.getElementById('modal-content');
        const successDiv = document.createElement('div');
        successDiv.className = 'modal-success';
        successDiv.textContent = message;

        modalBody.insertBefore(successDiv, modalBody.firstChild);
    }

    updateRow(data) {
        const row = document.querySelector(`tr[data-id="${data.id}"]`);
        if (!row) return;

        const cells = row.querySelectorAll('td');
        // 更新对应的单元格
        if (cells[0]) cells[0].textContent = data.sample_code;
        if (cells[3]) cells[3].textContent = data.collect_date;
        if (cells[4]) cells[4].textContent = data.collector;
        if (cells[5]) cells[5].textContent = data.collect_location;
    }

    removeRow(sampleId) {
        const row = document.querySelector(`tr[data-id="${sampleId}"]`);
        if (row) {
            row.remove();
        }
    }
}

// 全局函数，用于测试
window.openMassSpectrumModal = function(imageUrl) {
    const db = new StrainDatabase();
    db.openImageModal(imageUrl);
};

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    new StrainDatabase();
    console.log('StrainDatabase 初始化完成');
});