// File upload preview
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('files');
    const previewDiv = document.getElementById('upload-preview');

    if (fileInput && previewDiv) {
        fileInput.addEventListener('change', function() {
            previewDiv.innerHTML = '';
            if (this.files.length > 0) {
                const list = document.createElement('ul');
                list.className = 'list-group';
                
                Array.from(this.files).forEach(file => {
                    const item = document.createElement('li');
                    item.className = 'list-group-item d-flex justify-content-between align-items-center';
                    item.innerHTML = `
                        <span>
                            <i class="fas fa-file me-2"></i>
                            ${file.name}
                        </span>
                        <span class="badge bg-primary rounded-pill">${(file.size / 1024).toFixed(2)} KB</span>
                    `;
                    list.appendChild(item);
                });
                
                previewDiv.appendChild(list);
            }
        });
    }

    // Auto-close alerts
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            const closeButton = alert.querySelector('.btn-close');
            if (closeButton) {
                closeButton.click();
            }
        }, 5000);
    });
}); 