-- Skuter Rent database schema
CREATE DATABASE IF NOT EXISTS skuter_rent CHARACTER SET utf8mb4;
USE skuter_rent;

DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS gps_points;
DROP TABLE IF EXISTS rentals;
DROP TABLE IF EXISTS scooters;
DROP TABLE IF EXISTS staff;

CREATE TABLE scooters (
  id INT AUTO_INCREMENT PRIMARY KEY,
  label VARCHAR(50) NOT NULL,
  type ENUM('child','adult','child_car') NOT NULL,
  status ENUM('available','rented') NOT NULL DEFAULT 'available',
  location VARCHAR(100) DEFAULT 'Bole Road'
);

CREATE TABLE rentals (
  id INT AUTO_INCREMENT PRIMARY KEY,
  token VARCHAR(64) UNIQUE NOT NULL,
  scooter_id INT NOT NULL,
  renter_name VARCHAR(100) NOT NULL,
  renter_phone VARCHAR(30),
  renter_id_photo VARCHAR(255),
  scooter_type ENUM('child','adult','child_car') NOT NULL,
  start_time DATETIME NOT NULL,
  end_time DATETIME NULL,
  distance_km DECIMAL(6,2) NOT NULL DEFAULT 0,
  price DECIMAL(10,2) NOT NULL DEFAULT 0,
  amount_paid DECIMAL(10,2) NOT NULL DEFAULT 0,
  status ENUM('active','awaiting_payment','completed') NOT NULL DEFAULT 'active',
  payment_method ENUM('telebirr','cbe','cash') NULL,
  payment_status ENUM('unpaid','pending_confirmation','partially_paid','confirmed') NOT NULL DEFAULT 'unpaid',
  confirmed_by VARCHAR(50) NULL,
  confirmed_at DATETIME NULL,
  waiver_agreed TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (scooter_id) REFERENCES scooters(id)
);

-- Every payment AND refund is its own row here, each with its own receipt
-- number. A rental can have several payment rows (partial payments) and
-- several refund rows. rentals.amount_paid is kept as a running total of
-- confirmed payments minus confirmed refunds.
CREATE TABLE payments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  rental_id INT NOT NULL,
  receipt_number VARCHAR(20) UNIQUE NULL,
  kind ENUM('payment','refund') NOT NULL DEFAULT 'payment',
  amount DECIMAL(10,2) NOT NULL,
  method ENUM('telebirr','cbe','cash') NOT NULL,
  status ENUM('pending_confirmation','confirmed') NOT NULL DEFAULT 'pending_confirmation',
  note VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  confirmed_by VARCHAR(50) NULL,
  confirmed_at DATETIME NULL,
  FOREIGN KEY (rental_id) REFERENCES rentals(id)
);

CREATE TABLE gps_points (
  id INT AUTO_INCREMENT PRIMARY KEY,
  rental_id INT NOT NULL,
  lat DECIMAL(10,7) NOT NULL,
  lng DECIMAL(10,7) NOT NULL,
  recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rental_id) REFERENCES rentals(id)
);

CREATE TABLE staff (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(50) NOT NULL,
  pin VARCHAR(20) NOT NULL
);

-- Default staff PIN login (change this after first login)
INSERT INTO staff (name, pin) VALUES ('Admin', '1234');

-- Sample scooter fleet
INSERT INTO scooters (label, type) VALUES
('Child-01','child'), ('Child-02','child'), ('Child-03','child'),
('Adult-01','adult'), ('Adult-02','adult'), ('Adult-03','adult'), ('Adult-04','adult'),
('ChildCar-01','child_car'), ('ChildCar-02','child_car');
