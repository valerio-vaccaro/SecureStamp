# SecureStamp
A Flask-based file management system that allows users to securely upload and track files with timestamps.

## Features
- 🔐 User authentication (login/register)
- 📁 Multiple file uploads
- ⏱️ File timestamp tracking
- 👤 User-specific file management
- 🔒 Secure file storage

## Technical Stack
- 🐍 **Flask**: Web framework
- 🗄️ **MySQL**: Database
- 🔄 **Flask-SQLAlchemy**: SQL ORM
- 📦 **Flask-Migrate**: Database migrations
- 🔑 **Flask-Login**: User authentication
- ⚙️ **Python-dotenv**: Environment management
- 🛡️ **Werkzeug**: Secure file handling

## Project Setup

1. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create .env file:
```env
FLASK_APP=app.py
FLASK_ENV=development
DATABASE_URL=mysql://username:password@localhost/securestamp
SECRET_KEY=your-secret-key
UPLOAD_FOLDER=uploads
GPG_USER=gpg-user
ONION_URL=your-onion-address.onion

```

4. Initialize database:
```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

## Project Structure
```
SecureStamp/
├── app.py
├── config.py
├── models.py
├── routes.py
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   └── upload.html
├── static/
│   └── css/
├── uploads/
├── migrations/
└── requirements.txt
```

## Data Model

### Users Table
```sql
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    locked BOOLEAN DEFAULT TRUE NOT NULL
);
```

### Files Table
```sql
CREATE TABLE files (
    id INT PRIMARY KEY AUTO_INCREMENT,
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    user_id INT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_path VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'Timestamp requested' NOT NULL,
    file_downloads INT DEFAULT 0,
    timestamp_downloads INT DEFAULT 0,
    signature_downloads INT DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### Model Relationships
- 👥 One User can have many Files (one-to-many relationship)
- 📄 Each File belongs to exactly one User

### File Status
Possible file statuses:
- ⏳ `Timestamp requested`: Initial state after upload
- ✅ `Timestamp completed`: Timestamp has been generated
- ❌ `Error`: Error occurred during processing

## API Endpoints

### Authentication
- 🔐 `GET /register`: Display registration form
- 📝 `POST /register`: Register new user
  - Required fields: username, email, password
  - Returns: Redirect to login page or error message
- 🔑 `GET /login`: Display login form
- 📋 `POST /login`: User login
  - Required fields: username, password
  - Returns: Redirect to dashboard or error message
- 🚪 `GET /logout`: User logout
  - Returns: Redirect to login page

### File Management
- 📊 `GET /` or `GET /dashboard`: View user's dashboard
  - Returns: List of user's files
- 📤 `GET /upload`: Display file upload form
- ⬆️ `POST /upload`: Upload new file(s)
  - Required: files (multipart/form-data)
  - Returns: Success message or error
- 📂 `GET /files`: List user's files
  - Returns: All files belonging to the current user
- 🔍 `GET /files/<int:file_id>`: View file details
  - Returns: File information including SHA-256 hash
- ⬇️ `GET /download/<int:file_id>`: Download original file
  - Returns: File download
- ⏱️ `GET /download/timestamp/<int:file_id>`: Download timestamp file
  - Returns: .ots file download
- ✍️ `GET /download/signature/<int:file_id>`: Download signature file
  - Returns: .sig file download

### Security
- 🔒 All file management endpoints require authentication
- 🚫 File access is restricted to the owner
- 📊 File downloads are tracked with counters
- ✅ File extensions are validated
- 🔄 Files are stored with unique names

## Running the Application
```bash
flask run
```