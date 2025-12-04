Fix Python type hint issues for 2025 standards:

1. Search for deprecated type imports (typing.Dict, typing.List, typing.Optional)
2. Replace with modern syntax:
   - Dict[str, Any] -> dict[str, Any]
   - List[int] -> list[int]
   - Optional[X] -> X | None
3. Find unparameterized generics (bare dict, list) and add type parameters
4. Ensure all function signatures have return type hints
5. Fix async function types (use collections.abc.Coroutine if needed)
6. Run: mypy src/ or pylance check

Focus on files with recent modifications first.
