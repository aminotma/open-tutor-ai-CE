/**
 * Context Retrieval Engine Types
 * 
 * Type definitions for the Context Retrieval Engine API and responses.
 */

export type SourceType = 'pedagogical' | 'memory' | 'summary';
export type MemoryTypeForContext = 'episodic' | 'semantic' | 'procedural' | 'behavioral';
export type PedagogicalLevel = 'beginner' | 'intermediate' | 'advanced';

/**
 * Scores for a context item
 */
export interface ContextScores {
	/** Relevance to the query (0-1) */
	relevance: number;
	/** Engagement level based on item type and usage (0-1) */
	engagement: number;
	/** Recency score using exponential decay (0-1) */
	recency: number;
	/** Alignment with user preferences (0-1) */
	user_alignment: number;
	/** Composite score combining all weights (0-1) */
	composite: number;
	/** Score normalized within the result set (0-1) */
	normalized: number;
}

/**
 * Metadata for a context item
 */
export interface ContextMetadata {
	/** Type of content */
	type: string;
	/** Creation timestamp (Unix timestamp) */
	created_at?: number;
	/** Last update timestamp (Unix timestamp) */
	last_updated?: number;
	/** Source identifier */
	source_id: string;
	/** Content title if applicable */
	title?: string;
	/** Subject domain or category */
	subject_domain?: string;
	/** Additional custom metadata */
	[key: string]: unknown;
}

/**
 * Single context retrieval result
 */
export interface ContextItem {
	/** Ranking position in results (1-based) */
	rank: number;
	/** Source type: pedagogical document, memory, or summary */
	source: SourceType;
	/** Unique identifier for the source */
	source_id: string;
	/** First 300 characters of content for preview */
	content_preview: string;
	/** Full content */
	full_content: string;
	/** Metadata about the content */
	metadata: ContextMetadata;
	/** Score breakdown */
	scores: ContextScores;
}

/**
 * Request parameters for context retrieval
 */
export interface ContextRetrievalOptions {
	/** Search query (required) */
	query: string;
	/** Maximum number of results to return (default: 20, max: 50) */
	max_results?: number;
	/** Filter by specific source types */
	include_source_types?: SourceType[];
	/** Filter by memory types */
	memory_types?: MemoryTypeForContext[];
	/** User's pedagogical level for filtering */
	pedagogical_level?: PedagogicalLevel;
	/** User learning objectives to align retrieved context */
	learning_objectives?: string[];
}

/**
 * Statistics about available context sources
 */
export interface ContextStats {
	/** Current user ID */
	user_id: string;
	/** Total number of memories stored */
	total_memories: number;
	/** Count of memories by type */
	memory_types: Record<MemoryTypeForContext, number>;
	/** Available source types for this user */
	available_sources: SourceType[];
	/** Additional notes */
	note?: string;
}

/**
 * Context grouped by source type
 */
export interface ContextGroupedBySource {
	pedagogical: ContextItem[];
	memory: ContextItem[];
	summary: ContextItem[];
}

/**
 * Context grouped by memory type (for memory sources)
 */
export interface ContextGroupedByMemoryType {
	episodic: ContextItem[];
	semantic: ContextItem[];
	procedural: ContextItem[];
	behavioral: ContextItem[];
}
