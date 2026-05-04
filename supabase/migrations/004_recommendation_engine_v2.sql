ALTER TABLE engagements ADD COLUMN IF NOT EXISTS recommendation_config_json TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS unit_price DOUBLE PRECISION;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS unit_of_measure TEXT;
