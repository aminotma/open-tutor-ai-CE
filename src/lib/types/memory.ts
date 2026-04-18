export type MemoryType = 'episodic' | 'semantic' | 'procedural' | 'behavioral';

export interface MemoryResponse {
	id: string;
	memory_type: MemoryType;
	content: string;
	memory_metadata?: Record<string, unknown>;
	created_at?: number;
	updated_at?: number;
}
