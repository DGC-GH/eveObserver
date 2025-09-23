# EVE Observer Roadmap

This roadmap outlines the prioritized improvements for the EVE Observer project, based on code analysis and user feedback. Tasks are ordered for optimal execution, starting with critical bug fixes and progressing to enhancements.

## Phase 1: Bug Fixes and Debugging (High Priority)
1. **Debug competing contracts detection**  
   - Isolate contract comparison logic in a separate debug script  
   - Test with sample data and detailed logging  
   - Identify why detection returns 0 results  
   - Validate region filtering, price comparisons, and item matching  

2. **Fix competing contracts logic**  
   - Update contract processing functions based on debug findings  
   - Ensure checks for existing custom fields before adding/updating  
   - Add unit tests for contract comparison functionality  

3. **Clean up temporary debug files and logs**  
   - Remove debug scripts and excessive logging  
   - Consolidate logs to reduce clutter  
   - Commit cleanup as a separate change  

## Phase 2: Performance Optimizations (Medium Priority)
4. **Refactor async processing for blueprints**  
   - Convert ThreadPoolExecutor to asyncio.gather  
   - Improve concurrency and reduce overhead  
   - Benchmark to confirm speed improvements  

5. **Add type hints and input validation**  
   - Implement type hints across key Python modules  
   - Add validation for API data to prevent errors  
   - Enhance security and IDE integration  

## Phase 3: Testing and Quality Assurance (Medium Priority)
6. **Expand test coverage**  
   - Write integration tests for API calls  
   - Test data processing pipelines  
   - Aim for 80%+ code coverage  

## Phase 4: Tooling and Maintenance (Low Priority)
7. **Set up development tooling**  
   - Add pre-commit hooks for linting and formatting  
   - Update dependencies to latest stable versions  
   - Include security scanning  

8. **Modularize code and add benchmarks**  
   - Break down long functions into smaller units  
   - Add performance decorators for monitoring  
   - Document scalability improvements  

## Notes
- Always check for existing custom post types and fields before creating new ones
- Prioritize speed, simplicity, and security in all changes
- Test changes in a staging environment before production deployment
- Update documentation after each phase completion