import { create } from 'zustand'
import { daemon } from '../daemon'

interface MemorySearchResult {
  id: string
  type: 'fact' | 'episode' | 'procedure' | 'entity' | 'relationship'
  content: string
  score: number
  metadata?: Record<string, unknown>
}

interface MemoryState {
  searchResults: MemorySearchResult[]
  isSearching: boolean
  searchQuery: string
  setQuery: (query: string) => void
  performSearch: (query: string) => void
  clearResults: () => void
}

export const useMemoryStore = create<MemoryState>((set) => ({
  searchResults: [],
  isSearching: false,
  searchQuery: '',

  setQuery: (query: string) => set({ searchQuery: query }),

  performSearch: async (query: string) => {
    set({ isSearching: true, searchQuery: query, searchResults: [] })
    try {
      const result = await daemon.memorySearch(query)
      set({ searchResults: result, isSearching: false })
    } catch (err) {
      set({ isSearching: false })
    }
  },

  clearResults: () => set({ searchResults: [], searchQuery: '' }),
}))