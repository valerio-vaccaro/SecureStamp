class SecureStamp {
    async handleLogin(e) {
        e.preventDefault();
        const formData = new FormData(e.target);
        
        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    username: formData.get('username'),
                    password: formData.get('password')
                })
            });
    
            const data = await response.json();
    
            if (response.ok) {
                localStorage.setItem('token', data.token);
                this.token = data.token;
                this.showMainContent();
                await this.loadFiles();
            } else if (response.status === 403 && data.error === 'Account locked') {
                const lockedDate = new Date(data.locked_at).toLocaleString();
                alert(`Account locked: ${data.reason}\nLocked at: ${lockedDate}`);
            } else {
                alert('Login failed. Please check your credentials.');
            }
        } catch (error) {
            console.error('Login error:', error);
            alert('An error occurred during login.');
        }
    }
    
    // Add method to check account status
    async checkAccountStatus() {
        if (!this.token) return;
    
        try {
            const response = await fetch('/api/account/status', {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });
    
            if (response.ok) {
                const data = await response.json();
                if (data.status === 'locked') {
                    this.logout();
                    const lockedDate = new Date(data.locked_at).toLocaleString();
                    alert(`Account locked: ${data.reason}\nLocked at: ${lockedDate}`);
                }
            }
        } catch (error) {
            console.error('Error checking account status:', error);
        }
    }

    constructor() {
        this.token = localStorage.getItem('token');
        this.setupEventListeners();
        this.checkAuthStatus();

        // Check account status every 5 minutes
        if (this.token) {
            setInterval(() => this.checkAccountStatus(), 5 * 60 * 1000);
        }
    }

    setupEventListeners() {
        // Auth buttons
        document.getElementById('loginBtn').addEventListener('click', () => this.showLoginForm());
        document.getElementById('registerBtn').addEventListener('click', () => this.showRegisterForm());
        document.getElementById('logoutBtn').addEventListener('click', () => this.logout());

        // Forms
        document.getElementById('login-form').addEventListener('submit', (e) => this.handleLogin(e));
        document.getElementById('register-form').addEventListener('submit', (e) => this.handleRegister(e));
        document.getElementById('upload-form').addEventListener('submit', (e) => this.handleFileUpload(e));

        // Delegate click events for verify buttons
        document.getElementById('file-list').addEventListener('click', (e) => {
            if (e.target.classList.contains('download-btn')) {
                this.downloadFile(e.target.dataset.id, e.target.dataset.filename);
            }
            if (e.target.classList.contains('verify-btn')) {
                this.verifyFile(e.target.dataset.id);
            }
        });
    }

    async checkAuthStatus() {
        if (this.token) {
            this.showMainContent();
            await this.loadFiles();
        } else {
            this.showAuthForms();
        }
    }

    showLoginForm() {
        document.getElementById('registerForm').classList.add('d-none');
        document.getElementById('loginForm').classList.remove('d-none');
    }

    showRegisterForm() {
        document.getElementById('loginForm').classList.add('d-none');
        document.getElementById('registerForm').classList.remove('d-none');
    }

    showAuthForms() {
        document.getElementById('auth-forms').classList.remove('d-none');
        document.getElementById('main-content').classList.add('d-none');
        document.getElementById('auth-buttons').classList.remove('d-none');
        document.getElementById('user-nav').classList.add('d-none');
    }

    showMainContent() {
        document.getElementById('auth-forms').classList.add('d-none');
        document.getElementById('main-content').classList.remove('d-none');
        document.getElementById('auth-buttons').classList.add('d-none');
        document.getElementById('user-nav').classList.remove('d-none');
    }

    async handleLogin(e) {
        e.preventDefault();
        const formData = new FormData(e.target);
        
        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    username: formData.get('username'),
                    password: formData.get('password')
                })
            });

            if (response.ok) {
                const data = await response.json();
                localStorage.setItem('token', data.token);
                this.token = data.token;
                this.showMainContent();
                await this.loadFiles();
            } else {
                alert('Login failed. Please check your credentials.');
            }
        } catch (error) {
            console.error('Login error:', error);
            alert('An error occurred during login.');
        }
    }

    async handleRegister(e) {
        e.preventDefault();
        const formData = new FormData(e.target);
        
        try {
            const response = await fetch('/api/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    username: formData.get('username'),
                    email: formData.get('email'),
                    password: formData.get('password')
                })
            });

            if (response.ok) {
                alert('Registration successful! Please login.');
                this.showLoginForm();
            } else {
                alert('Registration failed. Please try again.');
            }
        } catch (error) {
            console.error('Registration error:', error);
            alert('An error occurred during registration.');
        }
    }

    async handleFileUpload(e) {
        e.preventDefault();
        const fileInput = document.getElementById('files');
        const files = fileInput.files;
        const uploadStatus = document.getElementById('upload-status');
        const progressBar = document.getElementById('upload-progress');
        const progressBarInner = progressBar.querySelector('.progress-bar');
        
        if (files.length === 0) {
            alert('Please select at least one file to upload.');
            return;
        }

        progressBar.classList.remove('d-none');
        uploadStatus.innerHTML = '';
        let successCount = 0;
        let failCount = 0;

        for (let i = 0; i < files.length; i++) {
            const formData = new FormData();
            formData.append('file', files[i]);

            try {
                // Update progress
                const progress = ((i + 1) / files.length) * 100;
                progressBarInner.style.width = `${progress}%`;
                progressBarInner.setAttribute('aria-valuenow', progress);

                // Update status
                uploadStatus.innerHTML += `<div>Uploading ${files[i].name}...</div>`;

                const response = await fetch('/api/stamp', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this.token}`
                    },
                    body: formData
                });

                if (response.ok) {
                    successCount++;
                    uploadStatus.innerHTML += `<div class="text-success">✓ ${files[i].name} uploaded successfully</div>`;
                } else {
                    failCount++;
                    uploadStatus.innerHTML += `<div class="text-danger">✗ Failed to upload ${files[i].name}</div>`;
                }
            } catch (error) {
                failCount++;
                uploadStatus.innerHTML += `<div class="text-danger">✗ Error uploading ${files[i].name}: ${error.message}</div>`;
            }
        }

        // Final status update
        const totalFiles = files.length;
        uploadStatus.innerHTML += `
            <div class="mt-2 ${successCount === totalFiles ? 'text-success' : 'text-warning'}">
                Upload complete: ${successCount} of ${totalFiles} files successful
            </div>
        `;

        // Reset form and refresh file list
        fileInput.value = '';
        await this.loadFiles();

        // Hide progress bar after a delay
        setTimeout(() => {
            progressBar.classList.add('d-none');
            progressBarInner.style.width = '0%';
        }, 3000);
    }

    async loadFiles() {
        try {
            const response = await fetch('/api/files', {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });

            if (response.ok) {
                const data = await response.json();
                // Sort files by uploaded_at date (newest first)
                data.files.sort((a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at));
                
                // Format dates
                data.files = data.files.map(file => ({
                    ...file,
                    uploaded_at: new Date(file.uploaded_at).toLocaleString(),
                    size_formatted: this.formatFileSize(file.size)
                }));
                
                const template = document.getElementById('file-template').innerHTML;
                const rendered = Mustache.render(template, data);
                document.getElementById('file-list').innerHTML = rendered;
            }
        } catch (error) {
            console.error('Error loading files:', error);
            document.getElementById('file-list').innerHTML = 
                '<div class="alert alert-danger">Error loading files. Please try again later.</div>';
        }
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async verifyFile(fileId) {
        try {
            const response = await fetch(`/api/verify/${fileId}`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });

            if (response.ok) {
                const data = await response.json();
                alert(`Verification Status: ${data.status}\nTimestamp: ${data.timestamp}\nBlockchain TX: ${data.blockchain_tx}`);
            } else {
                alert('Verification failed.');
            }
        } catch (error) {
            console.error('Verification error:', error);
            alert('An error occurred during verification.');
        }
    }

    async downloadFile(fileId, filename) {
        try {
            const response = await fetch(`/api/download/${fileId}`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });

            if (response.ok) {
                // Create a blob from the response
                const blob = await response.blob();
                // Create a temporary link element
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                // Append to body, click, and remove
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } else {
                const error = await response.json();
                alert(error.error || 'Download failed');
            }
        } catch (error) {
            console.error('Download error:', error);
            alert('An error occurred during download.');
        }
    }

    logout() {
        localStorage.removeItem('token');
        this.token = null;
        this.showAuthForms();
    }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    new SecureStamp();
}); 