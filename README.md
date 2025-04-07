# SecureStamp
A Flask-based file management system that allows users to securely upload and track files with timestamps.

## Features
- User authentication (login/register)
- Multiple file uploads
- File timestamp tracking
- User-specific file management
- Secure file storage

## Technical Stack
- **Flask**: Web framework
- **MySQL**: Database
- **Flask-SQLAlchemy**: SQL ORM
- **Flask-Migrate**: Database migrations
- **Flask-Login**: User authentication
- **Python-dotenv**: Environment management
- **Werkzeug**: Secure file handling

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

## Database Schema

### Users Table
```sql
CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

## API Endpoints

### Authentication
- `POST /auth/register`: Register new user
- `POST /auth/login`: User login
- `GET /auth/logout`: User logout

### File Management
- `GET /dashboard`: View uploaded files
- `POST /upload`: Upload new file(s)
- `GET /files`: List user's files
- `GET /files/<int:file_id>`: View file details

## Security Features
- Password hashing using Werkzeug
- Secure file upload handling
- User session management
- CSRF protection
- File extension validation
- User-specific file access control

## Running the Application
```bash
flask run
```
The application will be available at `http://localhost:5000`