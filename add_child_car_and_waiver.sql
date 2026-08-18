-- Run this in MySQL Workbench if your database already exists (don't
-- re-run schema.sql, it would wipe your data). Adds:
--   1. A new "Child Car" scooter/rental type (30 birr/min, no start fee)
--   2. A waiver_agreed column recording that each renter accepted the
--      safety & damage terms before starting their ride
USE skuter_rent;

ALTER TABLE scooters
  MODIFY type ENUM('child','adult','child_car') NOT NULL;

ALTER TABLE rentals
  MODIFY scooter_type ENUM('child','adult','child_car') NOT NULL;

ALTER TABLE rentals
  ADD COLUMN waiver_agreed TINYINT(1) NOT NULL DEFAULT 0 AFTER confirmed_at;

-- Mark all existing past rentals as agreed, since they were completed
-- before this waiver tracking existed (avoids showing them as "not agreed").
UPDATE rentals SET waiver_agreed = 1 WHERE status = 'completed';

-- Add a starter Child Car fleet -- rename/add more as needed in
-- MySQL Workbench or via a simple INSERT.
INSERT INTO scooters (label, type) VALUES
('ChildCar-01','child_car'), ('ChildCar-02','child_car');
