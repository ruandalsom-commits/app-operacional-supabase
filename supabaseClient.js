// Configuração do Supabase
const supabaseUrl = 'https://tgqjyyidogqxioqovhav.supabase.co';
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRncWp5eWlkb2dxeGlvcW92aGF2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk3Nzg4NjQsImV4cCI6MjA5NTM1NDg2NH0.Hprv50c9SB4aZXiQkWm49nutkN-Gde1Ve0OJR7mwTuk';

// O objeto "supabase" global é fornecido pelo CDN do supabase-js incluído no HTML
const supabaseClient = supabase.createClient(supabaseUrl, supabaseKey);
