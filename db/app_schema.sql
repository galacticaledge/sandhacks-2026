-- App tables (portable: runs on Tiger Data Postgres and on the local SQLite fallback).
CREATE TABLE IF NOT EXISTS source_fetches (
  source TEXT NOT NULL, fetched_at TIMESTAMPTZ NOT NULL, status TEXT NOT NULL,
  raw_path TEXT, detail TEXT, PRIMARY KEY (source, fetched_at));
CREATE TABLE IF NOT EXISTS flow_daily (
  date DATE PRIMARY KEY, mgd DOUBLE PRECISION, source TEXT);
CREATE TABLE IF NOT EXISTS flow_events (
  id TEXT PRIMARY KEY, published_at TIMESTAMPTZ, event_type TEXT, location_text TEXT,
  starts_at TIMESTAMPTZ, ends_at TIMESTAMPTZ, expected_flow_mgd DOUBLE PRECISION,
  flow_delta_mgd DOUBLE PRECISION, peak_flow_mgd DOUBLE PRECISION, confidence DOUBLE PRECISION,
  quote TEXT, source_url TEXT, entered_by TEXT);
CREATE TABLE IF NOT EXISTS model_runs (
  run_id TEXT PRIMARY KEY, scenario TEXT NOT NULL, issued_at TIMESTAMPTZ NOT NULL,
  params TEXT, k_mean DOUBLE PRECISION, k_var DOUBLE PRECISION, status TEXT, created_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS complaints (
  record_number TEXT PRIMARY KEY, received_at TIMESTAMPTZ, nature TEXT, city TEXT,
  lat DOUBLE PRECISION, lon DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS spills (
  site TEXT PRIMARY KEY, lat DOUBLE PRECISION, lon DOUBLE PRECISION, start_date TEXT,
  end_date TEXT, event_type TEXT, volume TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS subscriptions (
  id TEXT PRIMARY KEY, contact TEXT NOT NULL, channel TEXT NOT NULL, language TEXT NOT NULL,
  receptor_id TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, token TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS alerts_sent (
  subscription_id TEXT NOT NULL, night DATE NOT NULL, run_id TEXT NOT NULL, kind TEXT NOT NULL,
  sent_at TIMESTAMPTZ NOT NULL, status TEXT, PRIMARY KEY (subscription_id, night, run_id));
CREATE TABLE IF NOT EXISTS skill_scores (
  computed_at TIMESTAMPTZ NOT NULL, method TEXT NOT NULL, metric TEXT NOT NULL,
  site_id TEXT NOT NULL, value DOUBLE PRECISION, n INTEGER, note TEXT,
  PRIMARY KEY (method, metric, site_id));
CREATE TABLE IF NOT EXISTS web_reports (
  id TEXT PRIMARY KEY, url TEXT NOT NULL, source_name TEXT, title TEXT, published_at TIMESTAMPTZ,
  quote TEXT NOT NULL, topic TEXT, fetched_at TIMESTAMPTZ, via TEXT, search_query TEXT);
