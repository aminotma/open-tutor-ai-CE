#!/bin/bash

# Context Retrieval Engine - API Test Script
# This script demonstrates how to test the Context Retrieval Engine API

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

API_BASE_URL="http://localhost:8000/api/v1"
TOKEN="${AUTH_TOKEN:-your_bearer_token_here}"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Context Retrieval Engine - API Test Script               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}\n"

# Test 1: Check server is running
test_server_health() {
    echo -e "${YELLOW}[TEST 1]${NC} Checking server health..."
    response=$(curl -s -X POST http://localhost:8000/tutorai/health)
    
    if echo "$response" | grep -q "okay"; then
        echo -e "${GREEN}✓${NC} Server is running\n"
        return 0
    else
        echo -e "${RED}✗${NC} Server is not responding\n"
        return 1
    fi
}

# Test 2: Get context statistics
test_get_context_stats() {
    echo -e "${YELLOW}[TEST 2]${NC} Getting context statistics..."
    echo "Request: GET /context/stats"
    
    response=$(curl -s -X GET "$API_BASE_URL/context/stats" \
        -H "Accept: application/json" \
        -H "Authorization: Bearer $TOKEN")
    
    if echo "$response" | grep -q "total_memories"; then
        echo -e "${GREEN}✓${NC} Retrieved statistics:"
        echo "$response" | python -m json.tool
    else
        echo -e "${YELLOW}⚠${NC} No memories found or authentication issue"
        echo "Response: $response"
    fi
    echo ""
}

# Test 3: Retrieve context - basic query
test_retrieve_context_basic() {
    echo -e "${YELLOW}[TEST 3]${NC} Retrieving context - basic query..."
    echo "Request: POST /context/retrieve"
    
    request_body=$(cat <<'EOF'
{
  "query": "How to solve quadratic equations?",
  "max_results": 10,
  "pedagogical_level": "intermediate"
}
EOF
)
    
    echo "Body: $request_body"
    
    response=$(curl -s -X POST "$API_BASE_URL/context/retrieve" \
        -H "Accept: application/json" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d "$request_body")
    
    if echo "$response" | grep -q "rank"; then
        echo -e "${GREEN}✓${NC} Retrieved context items:"
        echo "$response" | python -m json.tool | head -50
        echo "... (truncated)"
    else
        echo -e "${YELLOW}⚠${NC} No results or error:"
        echo "$response" | python -m json.tool 2>/dev/null || echo "$response"
    fi
    echo ""
}

# Test 4: Retrieve context - with memory type filter
test_retrieve_context_filtered() {
    echo -e "${YELLOW}[TEST 4]${NC} Retrieving context - with filters..."
    echo "Request: POST /context/retrieve (with memory type filter)"
    
    request_body=$(cat <<'EOF'
{
  "query": "past exam results",
  "max_results": 5,
  "memory_types": ["episodic"],
  "include_source_types": ["memory"],
  "pedagogical_level": "advanced"
}
EOF
)
    
    echo "Body: $request_body"
    
    response=$(curl -s -X POST "$API_BASE_URL/context/retrieve" \
        -H "Accept: application/json" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d "$request_body")
    
    if echo "$response" | grep -q "source"; then
        echo -e "${GREEN}✓${NC} Retrieved filtered context:"
        echo "$response" | python -m json.tool | head -30
        echo "... (truncated)"
    else
        echo -e "${YELLOW}⚠${NC} No results:"
        echo "$response" | python -m json.tool 2>/dev/null || echo "$response"
    fi
    echo ""
}

# Test 5: Retrieve context - different pedagogical level
test_retrieve_context_levels() {
    echo -e "${YELLOW}[TEST 5]${NC} Testing pedagogical levels..."
    
    for level in "beginner" "intermediate" "advanced"; do
        echo "Level: $level"
        
        request_body=$(cat <<EOF
{
  "query": "introduction to algebra",
  "max_results": 3,
  "pedagogical_level": "$level"
}
EOF
)
        
        response=$(curl -s -X POST "$API_BASE_URL/context/retrieve" \
            -H "Accept: application/json" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $TOKEN" \
            -d "$request_body")
        
        count=$(echo "$response" | python -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
        echo "  Found: $count items"
    done
    echo ""
}

# Test 6: Score analysis
test_score_analysis() {
    echo -e "${YELLOW}[TEST 6]${NC} Analyzing scores from results..."
    
    request_body=$(cat <<'EOF'
{
  "query": "mathematics",
  "max_results": 1
}
EOF
)
    
    response=$(curl -s -X POST "$API_BASE_URL/context/retrieve" \
        -H "Accept: application/json" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d "$request_body")
    
    if echo "$response" | grep -q "scores"; then
        echo -e "${GREEN}✓${NC} Score breakdown:"
        echo "$response" | python -c "
import sys, json
data = json.load(sys.stdin)
if data:
    item = data[0]
    scores = item.get('scores', {})
    print(f'  Relevance:      {scores.get(\"relevance\", 0):.1%}')
    print(f'  Engagement:     {scores.get(\"engagement\", 0):.1%}')
    print(f'  Recency:        {scores.get(\"recency\", 0):.1%}')
    print(f'  User Alignment: {scores.get(\"user_alignment\", 0):.1%}')
    print(f'  ────────────────────────')
    print(f'  Composite:      {scores.get(\"composite\", 0):.1%}')
    print(f'  Normalized:     {scores.get(\"normalized\", 0):.1%}')
" 2>/dev/null
    fi
    echo ""
}

# Test 7: Error handling - missing query
test_error_missing_query() {
    echo -e "${YELLOW}[TEST 7]${NC} Testing error handling - missing query..."
    
    request_body='{"max_results": 10}'
    
    response=$(curl -s -X POST "$API_BASE_URL/context/retrieve" \
        -H "Accept: application/json" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d "$request_body")
    
    if echo "$response" | grep -q "error\|detail\|422"; then
        echo -e "${GREEN}✓${NC} Correctly rejected invalid request"
        echo "$response" | python -m json.tool 2>/dev/null || echo "$response"
    else
        echo -e "${YELLOW}⚠${NC} Unexpected response:"
        echo "$response"
    fi
    echo ""
}

# Test 8: Authorization error
test_auth_error() {
    echo -e "${YELLOW}[TEST 8]${NC} Testing authorization error..."
    
    request_body='{"query": "test"}'
    
    # Try with invalid token
    response=$(curl -s -X POST "$API_BASE_URL/context/retrieve" \
        -H "Accept: application/json" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer invalid_token" \
        -d "$request_body")
    
    if echo "$response" | grep -q "error\|Unauthorized\|401"; then
        echo -e "${GREEN}✓${NC} Correctly rejected invalid token"
    else
        echo -e "${YELLOW}⚠${NC} Check authentication (may be disabled in dev)"
    fi
    echo ""
}

# Main execution
main() {
    echo -e "${BLUE}Starting tests...${NC}\n"
    
    # Check if API is reachable
    if ! test_server_health; then
        echo -e "${RED}✗ Server not responding. Make sure it's running:${NC}"
        echo "  cd backend && python -m open_tutorai.main"
        exit 1
    fi
    
    # Set default token if not provided
    if [ "$TOKEN" = "your_bearer_token_here" ]; then
        echo -e "${YELLOW}⚠ Warning: Using placeholder token. Set AUTH_TOKEN environment variable:${NC}"
        echo "  export AUTH_TOKEN='your_actual_bearer_token'"
        echo ""
    fi
    
    # Run tests
    test_get_context_stats
    test_retrieve_context_basic
    test_retrieve_context_filtered
    test_retrieve_context_levels
    test_score_analysis
    test_error_missing_query
    test_auth_error
    
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║   Tests completed!                                         ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}\n"
}

# Run main
main
