import { TUTOR_API_BASE_URL } from '$lib/constants';
import type { MemoryType, MemoryResponse } from '$lib/types/memory';

export const getMemories = async (token: string, memoryType?: MemoryType) => {
	let error = null;

	let url = `${TUTOR_API_BASE_URL}/memories/`;
	if (memoryType) {
		url += `?memory_type=${encodeURIComponent(memoryType)}`;
	}

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
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res as MemoryResponse[];
};

export const addNewMemory = async (
	token: string,
	content: string,
	memoryType: MemoryType = 'semantic',
	memory_metadata?: Record<string, unknown>
) => {
	let error = null;

	const body = {
		content,
		memory_type: memoryType,
		memory_metadata,
	};

	const res = await fetch(`${TUTOR_API_BASE_URL}/memories/add`, {
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
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res as MemoryResponse;
};

export const updateMemoryById = async (
	token: string,
	id: string,
	content: string,
	memoryType?: MemoryType,
	memory_metadata?: Record<string, unknown>
) => {
	let error = null;

	const body = {
		content,
		memory_type: memoryType,
		memory_metadata,
	};

	const res = await fetch(`${TUTOR_API_BASE_URL}/memories/${id}/update`, {
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
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res as MemoryResponse;
};

export const queryMemory = async (
	token: string,
	query: string,
	memoryType?: MemoryType
) => {
	let error = null;

	const body = {
		query,
		memory_type: memoryType,
	};

	const res = await fetch(`${TUTOR_API_BASE_URL}/memories/query`, {
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
			error = err.detail;
			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res as MemoryResponse[];
};

export const deleteMemoryById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${TUTOR_API_BASE_URL}/memories/${id}`, {
		method: 'DELETE',
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteMemoriesByUserId = async (token: string) => {
	let error = null;

	const res = await fetch(`${TUTOR_API_BASE_URL}/memories/delete/user`, {
		method: 'DELETE',
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
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.log(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
