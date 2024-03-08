CREATE DATABASE IF NOT EXISTS xtream_code;
USE xtream_code;

-- Estructura de tabla para la tabla `users`
DROP TABLE IF EXISTS users;
CREATE TABLE IF NOT EXISTS users (
    id INT NOT NULL AUTO_INCREMENT,
    username VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci AUTO_INCREMENT=1;

-- Estructura de tabla para la tabla `stream_categories`
DROP TABLE IF EXISTS stream_categories;
CREATE TABLE IF NOT EXISTS stream_categories (
    id INT(11) NOT NULL AUTO_INCREMENT,
    category_name VARCHAR(255) COLLATE utf8_unicode_ci NOT NULL,
    parent_id INT(11) DEFAULT 0,
    cat_order INT(11) DEFAULT 0,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci AUTO_INCREMENT=1;

-- Insert categories
INSERT INTO stream_categories (category_name, parent_id, cat_order)
VALUES
('CULTURALES Y DOCUMENTALES', NULL, 1),
('DEPORTES', NULL, 2),
('INFANTIL', NULL, 3),
('INTERNATIONAL', NULL, 4),
('MUSICA', NULL, 5),
('NOTICIAS', NULL, 6),
('NOVELAS', NULL, 7),
('PELICULAS Y SERIES', NULL, 8),
('VIDA', NULL, 9),
('ARGENTINA', NULL, 10),
('ARUBA', NULL, 11),
('BELICE', NULL, 12),
('BOLIVIA', NULL, 13),
('BRASIL', NULL, 14),
('CHILE', NULL, 15),
('COLOMBIA', NULL, 16),
('COSTA RICA', NULL, 17),
('CUBA', NULL, 18),
('ECUADOR', NULL, 19),
('EL SALVADOR', NULL, 20),
('GUATEMALA', NULL, 21),
('HONDURAS', NULL, 22),
('MEXICO', NULL, 23),
('NICARAGUA', NULL, 24),
('PANAMA', NULL, 25),
('PARAGUAY', NULL, 26),
('PERU', NULL, 27),
('PUERTO RICO', NULL, 28),
('REPÚBLICA DOMINICANA', NULL, 29),
('URUGUAY', NULL, 30),
('VENEZUELA', NULL, 31);

-- Estructura de tabla para la tabla `streams`
DROP TABLE IF EXISTS streams;
CREATE TABLE IF NOT EXISTS streams (
    id INT NOT NULL AUTO_INCREMENT,
    num INT,
    name VARCHAR(255),
    stream_type VARCHAR(50),
    stream_id INT,
    stream_icon VARCHAR(255),
    epg_channel_id VARCHAR(255),
    added VARCHAR(255),
    is_adult INT,
    category_id INT,
    category_ids JSON,
    custom_sid VARCHAR(255),
    tv_archive INT,
    direct_source VARCHAR(255),
    tv_archive_duration INT,
    PRIMARY KEY (id),
    FOREIGN KEY (category_id) REFERENCES stream_categories(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci AUTO_INCREMENT=1;

-- Crear la tabla de información de usuario y servidor
CREATE TABLE IF NOT EXISTS user_server_info (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    user_info JSON,
    server_info JSON,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Crear la tabla de servidores DNS
CREATE TABLE IF NOT EXISTS server_dns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dns_url VARCHAR(255)
);

-- Insertar servidores DNS
INSERT INTO server_dns (dns_url)
VALUES
('http://iptvsub1-elite.com'),
('http://m3u.smartvent.me'),
('http://m3u.zen-ott.me'),
('http://m3u.star4k.me');
