#!/bin/bash
# Test script for the truesight-query endpoint

echo "Testing truesight-query endpoint..."
echo ""

# Test 1: Simple query
echo "Test 1: Total incidents query"
curl -X POST http://localhost:3000/api/tools/truesight-query \
  -H "Content-Type: application/json" \
  -d '{"utterance": "Show me total incidents last year"}' \
  -s | jq '.status, .answer'

echo ""
echo "---"
echo ""

# Test 2: Query with grouping
echo "Test 2: Incidents by area"
curl -X POST http://localhost:3000/api/tools/truesight-query \
  -H "Content-Type: application/json" \
  -d '{"utterance": "Show me incidents by area last year", "session_id": "test-session"}' \
  -s | jq '.status, .answer, .table | length'

echo ""
echo "---"
echo ""
echo "✓ Endpoint tests complete!"
