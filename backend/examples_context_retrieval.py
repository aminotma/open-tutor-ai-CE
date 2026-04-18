"""
Context Retrieval Engine - Example Usage

This file demonstrates how to use the Context Retrieval Engine API.
"""

import asyncio
import json
from datetime import datetime
from typing import Optional

# Example 1: Basic context retrieval
async def example_basic_retrieval():
    """
    Basic example: Retrieve context for a given query
    """
    print("=" * 80)
    print("EXAMPLE 1: Basic Context Retrieval")
    print("=" * 80)
    
    # In a real application, you would:
    # 1. Get the user token from authentication
    # 2. Make a POST request to /api/v1/context/retrieve
    
    example_request = {
        "query": "How to solve quadratic equations?",
        "max_results": 10,
        "pedagogical_level": "intermediate"
    }
    
    print("\nRequest:")
    print(json.dumps(example_request, indent=2))
    
    # Expected response structure
    example_response = [
        {
            "rank": 1,
            "source": "memory",
            "source_id": "mem_abc123",
            "content_preview": "Quadratic equations are solved using the quadratic formula...",
            "full_content": "Quadratic equations are second-degree polynomial equations...",
            "metadata": {
                "type": "semantic",
                "created_at": 1713476400,
                "last_updated": 1713562800,
                "source_id": "mem_abc123",
                "subject_domain": "mathematics"
            },
            "scores": {
                "relevance": 0.95,
                "engagement": 0.3,
                "recency": 0.75,
                "user_alignment": 0.5,
                "composite": 0.68,
                "normalized": 1.0
            }
        }
    ]
    
    print("\nExpected Response:")
    print(json.dumps(example_response, indent=2))


# Example 2: Retrieve with memory type filtering
async def example_memory_type_filtering():
    """
    Example: Retrieve context filtered by memory types
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Context Retrieval with Memory Type Filtering")
    print("=" * 80)
    
    example_request = {
        "query": "past exam results",
        "max_results": 5,
        "memory_types": ["episodic"],
        "include_source_types": ["memory"],
        "pedagogical_level": "advanced"
    }
    
    print("\nRequest (episodic memories only):")
    print(json.dumps(example_request, indent=2))
    
    # This would retrieve only episodic (experiential) memories
    print("\nNote: This retrieves only 'episodic' type memories")
    print("Memory types: episodic, semantic, procedural, behavioral")


# Example 3: Get context statistics
async def example_context_stats():
    """
    Example: Get statistics about available context sources
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Context Statistics")
    print("=" * 80)
    
    # In a real application:
    # GET /api/v1/context/stats
    
    example_stats = {
        "user_id": "user_12345",
        "total_memories": 42,
        "memory_types": {
            "episodic": 15,
            "semantic": 18,
            "procedural": 7,
            "behavioral": 2
        },
        "available_sources": ["memory"],
        "note": "Pedagogical documents and summaries support coming soon"
    }
    
    print("\nContext Statistics:")
    print(json.dumps(example_stats, indent=2))


# Example 4: Understanding scores
async def example_score_breakdown():
    """
    Example: Understanding the scoring system
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Understanding Scores")
    print("=" * 80)
    
    scores = {
        "relevance": 0.95,      # How relevant to the query (95%)
        "engagement": 0.30,     # User interaction history (30%)
        "recency": 0.75,        # How recent (exponential decay) (75%)
        "user_alignment": 0.50, # Alignment with user preferences (50%)
        "composite": 0.68,      # Weighted average (68%)
        "normalized": 1.0       # Relative to this result set (100% = highest)
    }
    
    print("\nScore Breakdown:")
    print(f"  Relevance:       {scores['relevance']:.1%}  (40% weight)")
    print(f"  Engagement:      {scores['engagement']:.1%}  (30% weight)")
    print(f"  Recency:         {scores['recency']:.1%}  (20% weight)")
    print(f"  User Alignment:  {scores['user_alignment']:.1%}  (10% weight)")
    print(f"  ─────────────────────────────────────")
    print(f"  Composite Score: {scores['composite']:.1%}")
    print(f"  Normalized:      {scores['normalized']:.1%}  (in this result set)")
    
    print("\nFormula:")
    print("  Composite = (0.4 × Relevance) + (0.3 × Engagement) +")
    print("              (0.2 × Recency) + (0.1 × User Alignment)")
    
    print("\nCalculation:")
    calc = (0.4 * 0.95) + (0.3 * 0.30) + (0.2 * 0.75) + (0.1 * 0.50)
    print(f"  = (0.4 × 0.95) + (0.3 × 0.30) + (0.2 × 0.75) + (0.1 × 0.50)")
    print(f"  = 0.38 + 0.09 + 0.15 + 0.05")
    print(f"  = {calc:.2f} (67%)")


# Example 5: Client-side usage (TypeScript)
async def example_typescript_usage():
    """
    Example: How to use the TypeScript client
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 5: TypeScript Client Usage")
    print("=" * 80)
    
    typescript_code = """
    import { retrieveContext, groupContextBySource } from '$lib/apis/context';
    
    // Basic retrieval
    const results = await retrieveContext(token, {
      query: "How to solve quadratic equations?",
      max_results: 10,
      pedagogical_level: "intermediate"
    });
    
    // Group by source
    const grouped = groupContextBySource(results);
    console.log(`Found ${grouped.memory.length} memory items`);
    
    // Display results
    results.forEach((item) => {
      console.log(`[${item.rank}] ${item.source}: ${item.content_preview}`);
      console.log(`    Relevance: ${Math.round(item.scores.composite * 100)}%`);
    });
    """
    
    print("\nTypeScript Usage:")
    print(typescript_code)


# Example 6: Advanced filtering
async def example_advanced_filtering():
    """
    Example: Advanced filtering and options
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 6: Advanced Filtering")
    print("=" * 80)
    
    # Scenario 1: Filter by multiple sources
    print("\n1. Retrieve from multiple source types:")
    request1 = {
        "query": "probability theory",
        "include_source_types": ["memory", "pedagogical"],
        "max_results": 20
    }
    print(json.dumps(request1, indent=2))
    
    # Scenario 2: Filter by multiple memory types
    print("\n2. Retrieve specific memory types:")
    request2 = {
        "query": "exam preparation",
        "memory_types": ["semantic", "procedural"],
        "pedagogical_level": "advanced"
    }
    print(json.dumps(request2, indent=2))
    
    # Scenario 3: Beginner-level content
    print("\n3. Beginner-level content only:")
    request3 = {
        "query": "introduction to algebra",
        "pedagogical_level": "beginner",
        "max_results": 15
    }
    print(json.dumps(request3, indent=2))


# Example 7: Utility functions
async def example_utility_functions():
    """
    Example: Using utility functions
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 7: Utility Functions")
    print("=" * 80)
    
    utility_examples = """
    import { 
      formatContextScores,
      filterContextByScore,
      groupContextBySource,
      getSourceLabel,
      getSourceIcon
    } from '$lib/apis/context';
    
    // Format scores for display
    const formatted = formatContextScores(item.scores);
    console.log(`Relevance: ${formatted.relevance}`); // "95%"
    
    // Filter by minimum score
    const highQuality = filterContextByScore(results, 0.7);
    console.log(`High quality results: ${highQuality.length}`);
    
    // Group results by source
    const grouped = groupContextBySource(results);
    grouped.memory.forEach(item => console.log(item.content_preview));
    
    // Get display labels
    console.log(getSourceLabel("memory"));       // "Your Memory"
    console.log(getSourceLabel("pedagogical"));  // "Learning Material"
    
    // Get icon classes
    console.log(getSourceIcon("memory"));        // "icon-brain"
    console.log(getSourceIcon("pedagogical"));   // "icon-book"
    """
    
    print("\nUtility Functions Usage:")
    print(utility_examples)


# Example 8: Error handling
async def example_error_handling():
    """
    Example: Error handling
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 8: Error Handling")
    print("=" * 80)
    
    error_handling_code = """
    import { retrieveContext } from '$lib/apis/context';
    
    try {
      const results = await retrieveContext(token, {
        query: "my query",
        max_results: 10
      });
      
      if (results.length === 0) {
        console.warn("No relevant context found");
      } else {
        console.log(`Found ${results.length} context items`);
      }
    } catch (error) {
      if (error === "Failed to retrieve context") {
        console.error("Context retrieval failed - server error");
      } else if (error === "Unauthorized") {
        console.error("Authentication required");
      } else {
        console.error("Unknown error:", error);
      }
    }
    """
    
    print("\nError Handling:")
    print(error_handling_code)


# Example 9: API Configuration
def example_configuration():
    """
    Example: Configuration in backend
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 9: Backend Configuration")
    print("=" * 80)
    
    config = """
    # In backend/open_tutorai/config.py
    
    CONTEXT_RETRIEVAL_CONFIG = {
        # Adjust relevance threshold (0.0 - 1.0)
        "filtering": {
            "relevance_threshold": 0.3,    # Minimum relevance to keep
            "recency_threshold": 0.1,      # Minimum recency score
            "max_age_days": 365,           # Maximum age of items
            "allow_level_gap": 1           # Max pedagogical level difference
        },
        
        # Adjust scoring weights
        "scoring": {
            "relevance_weight": 0.4,       # Query matching importance
            "engagement_weight": 0.3,      # User interaction importance
            "recency_weight": 0.2,         # Freshness importance
            "user_alignment_weight": 0.1   # Preference alignment importance
        },
        
        # Adjust output
        "output": {
            "max_results": 20,             # Default max results
            "diversity_strategy": True,    # Avoid source concentration
            "preview_length": 300          # Characters in preview
        }
    }
    """
    
    print("\nConfiguration:")
    print(config)


# Main execution
async def main():
    """Run all examples"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "  Context Retrieval Engine - Implementation Examples".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")
    
    await example_basic_retrieval()
    await example_memory_type_filtering()
    await example_context_stats()
    await example_score_breakdown()
    await example_typescript_usage()
    await example_advanced_filtering()
    await example_utility_functions()
    await example_error_handling()
    example_configuration()
    
    print("\n" + "=" * 80)
    print("End of Examples")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
