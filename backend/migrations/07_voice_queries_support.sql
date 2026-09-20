-- Migration 07: Voice and Audio Support for Nivaran AI
-- Adds message_type tracking to chat_history and performance indexes

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'chat_history' 
        AND column_name = 'message_type'
    ) THEN
        ALTER TABLE chat_history ADD COLUMN message_type VARCHAR(20) DEFAULT 'text';
    END IF;
END $$;

-- Index for filtering voice interactions and auditing
CREATE INDEX IF NOT EXISTS idx_chat_history_message_type ON chat_history(message_type);
CREATE INDEX IF NOT EXISTS idx_chat_history_user_type ON chat_history(user_id, message_type, created_at DESC);
