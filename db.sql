CREATE DATABASE securestamp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;   

CREATE USER 'securestamp'@'localhost' IDENTIFIED BY 'securestamp';

GRANT ALL PRIVILEGES ON securestamp.* TO 'securestamp'@'localhost';

FLUSH PRIVILEGES;