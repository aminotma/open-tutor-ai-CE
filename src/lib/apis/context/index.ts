/**
 * Context Retrieval Engine API Client
 * 
 * This module provides TypeScript/JavaScript functions to interact with the
 * Context Retrieval Engine backend API. It handles:
 * - Retrieving context from multiple sources (documents, memory, summaries)
 * - Getting context statistics
 */

import { TUTOR_API_BASE_URL } from '$lib/constants';

export interface ScoresSchema {
	relevance: number;
	engagement: number;
	recency: number;
	user_alignment: number;
	composite: number;
	normalized: number;
}

export interface MetadataSchema {
	type: string;
	created_at?: number;
	last_updated?: number;
	source_id: string;
	title?: string;
	subject_domain?: string;
}

export interface ContextRetrievalResponse {
	rank: number;
	source: 'pedagogical' | 'memory' | 'summary';
	source_id: string;
	content_preview: string;
	full_content: string;
	metadata: MetadataSchema;
	scores: ScoresSchema;
}

export interface ContextRetrievalRequest {
	query: string;
	max_results?: number;
	include_source_types?: ('pedagogical' | 'memory' | 'summary')[];
	memory_types?: ('episodic' | 'semantic' | 'procedural' | 'behavioral')[];
	pedagogical_level?: 'beginner' | 'intermediate' | 'advanced';
}

export interface ContextStatsResponse {
	user_id: string;
	total_memories: number;
	memory_types: {
		episodic: number;
		semantic: number;
		procedural: number;
		behavioral: number;
	};
	available_sources: string[];
	note?: string;
}

/**
 * Retrieve context from multiple sources
 * 
 * Combines:
 * - Pedagogical documents (RAG)
 * - Internal memory (episodic, semantic, procedural, behavioral)
 * - Generated summaries
 * 
 * Results are filtered and ranked by pedagogical relevance.
 * 
 * @param token - Authentication token
 * @param request - Context retrieval request parameters
 * @returns List of context items ranked by relevance
 * @throws Error if the request fails
 * 
 * @example
 * const context = await retrieveContext(token, {
 *   query: "How to solve quadratic equations?",
 *   max_results: 10,
 *   pedagogical_level: "intermediate"
 * });
 */
export const retrieveContext = async (
	token: string,
	request: ContextRetrievalRequest
): Promise<ContextRetrievalResponse[]> => {
	let error = null;

	const url = `${TUTOR_API_BASE_URL}/context/retrieve`;

	// Prepare request body
	const body: Record<string, unknown> = {
		query: request.query,
		max_results: request.max_results ?? 20,
	};

	if (request.include_source_types) {
		body.include_source_types = request.include_source_types;
	}

	if (request.memory_types) {
		body.memory_types = request.memory_types;
	}

	if (request.pedagogical_level) {
		body.pedagogical_level = request.pedagogical_level;
	}

	const res = await fetch(url, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(body)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || 'Failed to retrieve context';
			console.log('Context retrieval error:', err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res as ContextRetrievalResponse[];
};

/**
 * Get context statistics for the current user
 * 
 * Returns information about available context sources:
 * - Total number of memories
 * - Breakdown by memory type
 * - Available source types
 * 
 * @param token - Authentication token
 * @returns Context statistics
 * @throws Error if the request fails
 * 
 * @example
 * const stats = await getContextStats(token);
 * console.log(`You have ${stats.total_memories} memories stored`);
 */
export const getContextStats = async (token: string): Promise<ContextStatsResponse> => {
	let error = null;

	const url = `${TUTOR_API_BASE_URL}/context/stats`;

	const res = await fetch(url, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail || err.message || 'Failed to get context stats';
			console.log('Context stats error:', err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res as ContextStatsResponse;
};

/**
 * Retrieve context with pedagogical memory types filter
 * 
 * Convenience function to retrieve context filtered by specific memory types
 * 
 * @param token - Authentication token
 * @param query - Search query
 * @param memoryTypes - Array of memory types to filter by
 * @param maxResults - Maximum number of results
 * @returns List of context items filtered by memory type
 * 
 * @example
 * const episodicContext = await retrieveContextByMemoryType(
 *   token,
 *   "past exam results",
 *   ["episodic"],
 *   10
 * );
 */
export const retrieveContextByMemoryType = async (
	token: string,
	query: string,
	memoryTypes: ('episodic' | 'semantic' | 'procedural' | 'behavioral')[],
	maxResults: number = 20
): Promise<ContextRetrievalResponse[]> => {
	return retrieveContext(token, {
		query,
		memory_types: memoryTypes,
		max_results: maxResults,
		include_source_types: ['memory']
	});
};

/**
 * Retrieve context from specific sources only
 * 
 * Convenience function to retrieve context from specific source types
 * 
 * @param token - Authentication token
 * @param query - Search query
 * @param sourceTypes - Array of source types to retrieve from
 * @param maxResults - Maximum number of results
 * @returns List of context items from specified sources
 * 
 * @example
 * const memoryContext = await retrieveContextFromSources(
 *   token,
 *   "calculus help",
 *   ["memory", "pedagogical"],
 *   15
 * );
 */
export const retrieveContextFromSources = async (
	token: string,
	query: string,
	sourceTypes: ('pedagogical' | 'memory' | 'summary')[],
	maxResults: number = 20
): Promise<ContextRetrievalResponse[]> => {
	return retrieveContext(token, {
		query,
		include_source_types: sourceTypes,
		max_results: maxResults
	});
};

/**
 * Format context scores for display
 * 
 * Converts scores to percentage format for UI display
 * 
 * @param scores - Raw scores object
 * @returns Formatted scores object with percentages
 * 
 * @example
 * const formattedScores = formatContextScores(contextItem.scores);
 * console.log(`Relevance: ${formattedScores.relevance}%`);
 */
export const formatContextScores = (scores: ScoresSchema): Record<string, string> => {
	return {
		relevance: `${Math.round(scores.relevance * 100)}%`,
		engagement: `${Math.round(scores.engagement * 100)}%`,
		recency: `${Math.round(scores.recency * 100)}%`,
		user_alignment: `${Math.round(scores.user_alignment * 100)}%`,
		composite: `${Math.round(scores.composite * 100)}%`,
		normalized: `${Math.round(scores.normalized * 100)}%`
	};
};

/**
 * Filter context results by minimum composite score
 * 
 * Utility function to filter context results by score threshold
 * 
 * @param results - Array of context results
 * @param minScore - Minimum composite score (0-1)
 * @returns Filtered results with scores above threshold
 * 
 * @example
 * const highQualityContext = filterContextByScore(results, 0.7);
 */
export const filterContextByScore = (
	results: ContextRetrievalResponse[],
	minScore: number
): ContextRetrievalResponse[] => {
	return results.filter((item) => item.scores.composite >= minScore);
};

/**
 * Group context results by source type
 * 
 * Utility function to organize context results by their source
 * 
 * @param results - Array of context results
 * @returns Object with results grouped by source type
 * 
 * @example
 * const grouped = groupContextBySource(results);
 * console.log(`Found ${grouped.memory.length} memory sources`);
 */
export const groupContextBySource = (
	results: ContextRetrievalResponse[]
): Record<string, ContextRetrievalResponse[]> => {
	const grouped: Record<string, ContextRetrievalResponse[]> = {
		pedagogical: [],
		memory: [],
		summary: []
	};

	for (const item of results) {
		const source = item.source as keyof typeof grouped;
		if (source in grouped) {
			grouped[source].push(item);
		}
	}

	return grouped;
};

/**
 * Get source icon class for UI rendering
 * 
 * Maps source types to icon identifiers for UI display
 * 
 * @param source - Source type
 * @returns Icon class name
 * 
 * @example
 * const icon = getSourceIcon("memory");
 * // Returns "icon-memory" or appropriate icon class
 */
export const getSourceIcon = (source: 'pedagogical' | 'memory' | 'summary'): string => {
	const iconMap = {
		pedagogical: 'icon-book',
		memory: 'icon-brain',
		summary: 'icon-file-text'
	};

	return iconMap[source] || 'icon-document';
};

/**
 * Get source label for UI display
 * 
 * Provides human-readable labels for source types
 * 
 * @param source - Source type
 * @returns Display label
 * 
 * @example
 * const label = getSourceLabel("memory");
 * // Returns "Your Memory"
 */
export const getSourceLabel = (source: 'pedagogical' | 'memory' | 'summary'): string => {
	const labelMap = {
		pedagogical: 'Learning Material',
		memory: 'Your Memory',
		summary: 'Summary'
	};

	return labelMap[source] || 'Unknown Source';
};
