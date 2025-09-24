"""
EVE Observer Contract Processor
Main orchestrator for contract processing operations.
"""

# Re-export all functions from the new modular structure for backward compatibility
from contract_bpo import (
    compare_contracts,
    filter_single_bpo_contracts,
    get_user_single_bpo_contracts,
    save_bpo_contracts,
)
from contract_competition import (
    check_contract_competition,
    check_contract_competition_hybrid,
    check_contracts_competition_concurrent,
)
from contract_expansion import (
    apply_cached_data_to_contracts,
    build_blueprint_contracts_cache,
    expand_all_contracts_async,
    expand_new_contracts_dynamic,
    expand_single_contract_with_caching,
    fetch_and_expand_all_forge_contracts,
)
from contract_fetching import (
    fetch_all_contracts_in_region,
    fetch_character_contract_items,
    fetch_character_contracts,
    fetch_corporation_contract_items,
    fetch_corporation_contracts,
    get_issuer_names,
    get_region_from_location,
)
from contract_processor_new import (
    contract_counter,
    fetch_all_contract_items_for_contracts,
    get_user_contracts,
    main,
    process_character_contracts,
    update_contract_cache_only,
)
from contract_wordpress import (
    batch_update_contracts_in_wp,
    cleanup_contract_posts,
    generate_contract_title,
    update_contract_in_wp,
    update_contract_in_wp_with_competition_result,
)

# For backward compatibility, also import the main function
__all__ = [
    # Competition analysis
    "check_contract_competition",
    "check_contract_competition_hybrid",
    "check_contracts_competition_concurrent",
    # Contract fetching
    "fetch_character_contract_items",
    "fetch_corporation_contract_items",
    "fetch_character_contracts",
    "fetch_corporation_contracts",
    "fetch_all_contracts_in_region",
    "get_region_from_location",
    "get_issuer_names",
    # Contract expansion
    "expand_single_contract_with_caching",
    "expand_new_contracts_dynamic",
    "expand_all_contracts_async",
    "apply_cached_data_to_contracts",
    "fetch_and_expand_all_forge_contracts",
    "build_blueprint_contracts_cache",
    # WordPress integration
    "generate_contract_title",
    "update_contract_in_wp",
    "update_contract_in_wp_with_competition_result",
    "batch_update_contracts_in_wp",
    "cleanup_contract_posts",
    # BPO functions
    "save_bpo_contracts",
    "filter_single_bpo_contracts",
    "get_user_single_bpo_contracts",
    "compare_contracts",
    # Main processing
    "process_character_contracts",
    "update_contract_cache_only",
    "get_user_contracts",
    "fetch_all_contract_items_for_contracts",
    "contract_counter",
    "main",
]
