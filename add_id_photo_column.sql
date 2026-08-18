-- Run this in MySQL Workbench if you already created the skuter_rent database
-- (adds the missing renter_id_photo column without losing your existing data)
USE skuter_rent;
ALTER TABLE rentals ADD COLUMN renter_id_photo VARCHAR(255) AFTER renter_phone;
