-- Supabase SQL Schema for Revisión LNC Application
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard > SQL Editor

-- Table: inscripciones (Sessions storage)
CREATE TABLE IF NOT EXISTS inscripciones (
    name TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    data JSONB NOT NULL,
    columns JSONB
);

-- Table: config (Rules, equivalences, categories)
CREATE TABLE IF NOT EXISTS config (
    name TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table: licencias_cache (FESBA license database)
CREATE TABLE IF NOT EXISTS licencias_cache (
    name TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    count INTEGER DEFAULT 0,
    data JSONB NOT NULL
);

-- Enable Row Level Security (optional - for production)
-- ALTER TABLE inscripciones ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE config ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE licencias_cache ENABLE ROW LEVEL SECURITY;

-- Grant access for anon key (required for app to work)
-- CREATE POLICY "Enable read access for all users" ON inscripciones FOR SELECT USING (true);
-- CREATE POLICY "Enable insert access for all users" ON inscripciones FOR INSERT WITH CHECK (true);
-- CREATE POLICY "Enable update access for all users" ON inscripciones FOR UPDATE USING (true);
-- CREATE POLICY "Enable delete access for all users" ON inscripciones FOR DELETE USING (true);
