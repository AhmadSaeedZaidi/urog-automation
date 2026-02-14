-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ==========================================
-- ENUM DEFINITIONS (Type Safety)
-- ==========================================
CREATE TYPE user_role AS ENUM ('student', 'professor', 'admin', 'external');
CREATE TYPE opp_status AS ENUM ('open', 'closed', 'draft', 'archived');
CREATE TYPE app_status AS ENUM ('pending', 'accepted', 'rejected', 'interview');
CREATE TYPE msg_platform AS ENUM ('email', 'whatsapp');
CREATE TYPE msg_status AS ENUM ('queued', 'sent', 'failed');

-- ==========================================
-- 1. BRONZE LAYER (The Ingestion Inbox)
-- ==========================================
CREATE TABLE IF NOT EXISTS data_inbox (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_name TEXT NOT NULL,       -- e.g., "Fall Recruitment Form", "Education Team CSV"
    source_type TEXT NOT NULL,       -- e.g., "google_form", "csv", "manual_entry"
    raw_payload JSONB NOT NULL,      -- untouched data
    processed_at TIMESTAMP WITH TIME ZONE,
    error_log TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ==========================================
-- 2. SILVER LAYER (Core Normalized Data)
-- ==========================================

CREATE TABLE IF NOT EXISTS people (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    role user_role DEFAULT 'student',
    phone TEXT, 
    
    profile_data JSONB DEFAULT '{}', -- Flexible metadata (Team, Year, Major, T-Shirt Size)
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Opportunities (Projects, Research, Jobs)
CREATE TABLE IF NOT EXISTS opportunities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    description TEXT,
    owner_id UUID REFERENCES people(id),
    status opp_status DEFAULT 'draft',
    type TEXT,                       -- research, internship, event (Keep text if highly variable)
    requirements JSONB DEFAULT '{}', -- e.g. {"min_gpa": 3.0}
    form_config JSONB DEFAULT '{}',  -- Stores Google Form ID/Link
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Applications (Linking People to Opportunities)
CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    applicant_id UUID REFERENCES people(id),
    opportunity_id UUID REFERENCES opportunities(id),
    status app_status DEFAULT 'pending', -- Uses the Enum
    submission_data JSONB DEFAULT '{}', -- The form answers specific to this app
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(applicant_id, opportunity_id)
);

-- ==========================================
-- 3. AUTOMATION LAYER (Templates & Logs)
-- ==========================================

CREATE TABLE IF NOT EXISTS templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,       -- e.g. "Acceptance Email", "WhatsApp Alert"
    platform msg_platform NOT NULL,
    content TEXT NOT NULL,           -- The Jinja2 or f-string template
    required_keys TEXT[],            -- Keys needed from profile_data
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sent_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    recipient_id UUID REFERENCES people(id),
    template_id UUID REFERENCES templates(id),
    platform msg_platform,
    status msg_status DEFAULT 'queued',
    compiled_message TEXT,           -- Audit what was actually sent
    error_message TEXT,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);