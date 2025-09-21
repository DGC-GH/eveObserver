<?php
/**
 * Plugin Name: EVE Observer
 * Plugin URI: https://github.com/DGC-GH/eveObserver
 * Description: A custom WordPress plugin for EVE Online dashboard with ESI API integration.
 * Version: 1.0.0
 * Author: DGC-GH
 * License: GPL v2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: eve-observer
 * Requires at least: 5.0
 * Tested up to: 6.0
 * Requires PHP: 7.4
 */

// Prevent direct access
if (!defined('ABSPATH')) {
    exit;
}

// Main plugin class
class EVE_Observer {

    public function __construct() {
        // Hook into WordPress
        add_action('init', array($this, 'init'));
        add_action('admin_menu', array($this, 'add_admin_menu'));
        add_action('admin_enqueue_scripts', array($this, 'enqueue_admin_scripts'));
        register_activation_hook(__FILE__, array($this, 'activate'));
        register_deactivation_hook(__FILE__, array($this, 'deactivate'));
    }

    public function init() {
        // Register meta for REST API
        register_meta('post', '_eve_planet_pins_data', array(
            'show_in_rest' => true,
            'single' => true,
            'type' => 'string',
            'auth_callback' => '__return_true'
        ));

        // Character meta fields
        $char_meta_fields = array(
            '_eve_char_id', '_eve_char_name', '_eve_corporation_id', '_eve_alliance_id',
            '_eve_birthday', '_eve_gender', '_eve_race_id', '_eve_bloodline_id',
            '_eve_ancestry_id', '_eve_security_status', '_eve_total_sp', '_eve_last_updated',
            '_eve_wallet_balance', '_eve_location_id', '_eve_location_name', '_eve_assets_data',
            '_eve_killmails_data', '_eve_clones_data', '_eve_implants_data', '_eve_standings_data'
        );
        $numeric_char_fields = array('_eve_char_id', '_eve_corporation_id', '_eve_alliance_id', '_eve_race_id', '_eve_bloodline_id', '_eve_ancestry_id', '_eve_security_status', '_eve_total_sp', '_eve_wallet_balance', '_eve_location_id');
        foreach ($char_meta_fields as $field) {
            register_meta('post', $field, array(
                'show_in_rest' => true,
                'single' => true,
                'type' => in_array($field, $numeric_char_fields) ? 'number' : 'string',
                'auth_callback' => '__return_true'
            ));
        }

        // Blueprint meta fields
        $bp_meta_fields = array(
            '_eve_bp_item_id', '_eve_bp_type_id', '_eve_bp_location_id', '_eve_bp_quantity',
            '_eve_bp_me', '_eve_bp_te', '_eve_bp_runs', '_eve_char_id', '_eve_last_updated',
            '_eve_bp_location_name'
        );
        $numeric_bp_fields = array('_eve_bp_item_id', '_eve_bp_type_id', '_eve_bp_location_id', '_eve_bp_quantity', '_eve_bp_me', '_eve_bp_te', '_eve_bp_runs', '_eve_char_id');
        foreach ($bp_meta_fields as $field) {
            register_meta('post', $field, array(
                'show_in_rest' => true,
                'single' => true,
                'type' => in_array($field, $numeric_bp_fields) ? 'number' : 'string',
                'auth_callback' => '__return_true'
            ));
        }

        // Planet meta fields
        $planet_meta_fields = array(
            '_eve_planet_id', '_eve_planet_type', '_eve_planet_solar_system_id',
            '_eve_planet_upgrade_level', '_eve_char_id', '_eve_last_updated'
        );
        $numeric_planet_fields = array('_eve_planet_id', '_eve_planet_solar_system_id', '_eve_planet_upgrade_level', '_eve_char_id');
        foreach ($planet_meta_fields as $field) {
            register_meta('post', $field, array(
                'show_in_rest' => true,
                'single' => true,
                'type' => in_array($field, $numeric_planet_fields) ? 'number' : 'string',
                'auth_callback' => '__return_true'
            ));
        }

        // Corporation meta fields
        $corp_meta_fields = array(
            '_eve_corp_id', '_eve_corp_name', '_eve_corp_ticker', '_eve_corp_member_count',
            '_eve_corp_ceo_id', '_eve_corp_alliance_id', '_eve_corp_tax_rate', '_eve_last_updated',
            '_eve_corp_wallet_balance', '_eve_corp_assets_data', '_eve_corp_blueprints_data',
            '_eve_corp_industry_jobs_data', '_eve_corp_orders_data', '_eve_corp_structures_data'
        );
        $numeric_corp_fields = array('_eve_corp_id', '_eve_corp_member_count', '_eve_corp_ceo_id', '_eve_corp_alliance_id', '_eve_corp_tax_rate', '_eve_corp_wallet_balance');
        foreach ($corp_meta_fields as $field) {
            register_meta('post', $field, array(
                'show_in_rest' => true,
                'single' => true,
                'type' => in_array($field, $numeric_corp_fields) ? 'number' : 'string',
                'auth_callback' => '__return_true'
            ));
        }

        // Contract meta fields
        $contract_meta_fields = array(
            '_eve_contract_id', '_eve_contract_type', '_eve_contract_status', '_eve_contract_title',
            '_eve_contract_for_corp', '_eve_contract_issuer_id', '_eve_contract_issuer_corp_id',
            '_eve_contract_assignee_id', '_eve_contract_acceptor_id', '_eve_contract_start_location_id', '_eve_contract_end_location_id', '_eve_contract_date_issued',
            '_eve_contract_date_expired', '_eve_contract_date_accepted', '_eve_contract_date_completed',
            '_eve_contract_price', '_eve_contract_reward', '_eve_contract_collateral', '_eve_contract_buyout',
            '_eve_contract_volume', '_eve_contract_days_to_complete', '_eve_contract_entity_id', '_eve_contract_items', '_eve_last_updated',
            '_eve_contract_outbid', '_eve_contract_market_price', '_eve_contract_region_id'
        );
        $numeric_contract_fields = array('_eve_contract_id', '_eve_contract_issuer_id', '_eve_contract_issuer_corp_id', '_eve_contract_assignee_id', '_eve_contract_acceptor_id', '_eve_contract_price', '_eve_contract_reward', '_eve_contract_collateral', '_eve_contract_buyout', '_eve_contract_volume', '_eve_contract_days_to_complete', '_eve_contract_market_price');
        foreach ($contract_meta_fields as $field) {
            register_meta('post', $field, array(
                'show_in_rest' => true,
                'single' => true,
                'type' => in_array($field, $numeric_contract_fields) ? 'number' : 'string',
                'auth_callback' => '__return_true'
            ));
        }

        // Register meta for REST API
        register_meta('post', '_thumbnail_external_url', array(
            'show_in_rest' => true,
            'single' => true,
            'type' => 'string',
            'auth_callback' => '__return_true'
        ));

        // Hook to handle external featured images
        add_filter('post_thumbnail_html', array($this, 'post_thumbnail_external_url'), 10, 5);
        add_filter('get_post_thumbnail_id', array($this, 'get_post_thumbnail_id_external'), 10, 1);

        // Add thumbnail columns to admin list tables
        add_filter('manage_eve_character_posts_columns', array($this, 'add_thumbnail_column'));
        add_action('manage_eve_character_posts_custom_column', array($this, 'display_thumbnail_column'), 10, 2);
        
        add_filter('manage_eve_blueprint_posts_columns', array($this, 'add_thumbnail_column'));
        add_action('manage_eve_blueprint_posts_custom_column', array($this, 'display_thumbnail_column'), 10, 2);
        
        add_filter('manage_eve_planet_posts_columns', array($this, 'add_thumbnail_column'));
        add_action('manage_eve_planet_posts_custom_column', array($this, 'display_thumbnail_column'), 10, 2);
        
        add_filter('manage_eve_corporation_posts_columns', array($this, 'add_thumbnail_column'));
        add_action('manage_eve_corporation_posts_custom_column', array($this, 'display_thumbnail_column'), 10, 2);
        
        add_filter('manage_eve_contract_posts_columns', array($this, 'add_thumbnail_column'));
        add_action('manage_eve_contract_posts_custom_column', array($this, 'display_thumbnail_column'), 10, 2);

        // Add outbid column to contracts
        add_filter('manage_eve_contract_posts_columns', array($this, 'add_outbid_column'));
        add_action('manage_eve_contract_posts_custom_column', array($this, 'display_outbid_column'), 10, 2);
        add_filter('manage_edit-eve_contract_sortable_columns', array($this, 'make_outbid_column_sortable'));
        add_action('pre_get_posts', array($this, 'sort_outbid_column'));

        // Register custom post types
        $this->register_custom_post_types();
    }

    public function add_admin_menu() {
        add_menu_page(
            'EVE Observer Dashboard',
            'EVE Observer',
            'manage_options',
            'eve-observer',
            array($this, 'display_dashboard'),
            'dashicons-chart-line',
            30
        );

        // Add submenus for CPTs
        add_submenu_page('eve-observer', 'Dashboard', 'Dashboard', 'manage_options', 'eve-observer');
        add_submenu_page('eve-observer', 'Characters', 'Characters', 'manage_options', 'edit.php?post_type=eve_character');
        add_submenu_page('eve-observer', 'Blueprints', 'Blueprints', 'manage_options', 'edit.php?post_type=eve_blueprint');
        add_submenu_page('eve-observer', 'Planets', 'Planets', 'manage_options', 'edit.php?post_type=eve_planet');
        add_submenu_page('eve-observer', 'Corporations', 'Corporations', 'manage_options', 'edit.php?post_type=eve_corporation');
        add_submenu_page('eve-observer', 'Contracts', 'Contracts', 'manage_options', 'edit.php?post_type=eve_contract');
    }

    public function enqueue_admin_scripts($hook) {
        // Add clipboard functionality for all admin pages
        wp_add_inline_script('jquery', '
            function copyToClipboard(text) {
                if (navigator.clipboard && window.isSecureContext) {
                    navigator.clipboard.writeText(text).then(function() {
                        showCopyFeedback("Link copied to clipboard!");
                    }).catch(function(err) {
                        console.error("Failed to copy: ", err);
                        fallbackCopyTextToClipboard(text);
                    });
                } else {
                    fallbackCopyTextToClipboard(text);
                }
            }
            
            function fallbackCopyTextToClipboard(text) {
                var textArea = document.createElement("textarea");
                textArea.value = text;
                textArea.style.position = "fixed";
                textArea.style.left = "-999999px";
                textArea.style.top = "-999999px";
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                try {
                    var successful = document.execCommand("copy");
                    if (successful) {
                        showCopyFeedback("Link copied to clipboard!");
                    } else {
                        showCopyFeedback("Copy failed", true);
                    }
                } catch (err) {
                    showCopyFeedback("Copy failed: " + err, true);
                }
                document.body.removeChild(textArea);
            }
            
            function showCopyFeedback(message, isError) {
                var existing = document.querySelector(".copy-feedback");
                if (existing) {
                    existing.remove();
                }
                
                var feedback = document.createElement("div");
                feedback.className = "copy-feedback";
                feedback.innerHTML = message;
                feedback.style.cssText = "position:fixed;top:20px;right:20px;background:" + (isError ? "#dc3545" : "#28a745") + ";color:white;padding:10px 15px;border-radius:4px;z-index:9999;font-weight:bold;box-shadow:0 2px 10px rgba(0,0,0,0.2);";
                document.body.appendChild(feedback);
                
                setTimeout(function() {
                    if (feedback.parentNode) {
                        feedback.parentNode.removeChild(feedback);
                    }
                }, 3000);
            }
        ');

        // Dashboard-specific scripts and styles
        if ($hook === 'toplevel_page_eve-observer') {
            wp_enqueue_style('eve-observer-dashboard', plugin_dir_url(__FILE__) . 'css/dashboard.css', array(), '1.0.0');
            wp_enqueue_script('chart-js', 'https://cdn.jsdelivr.net/npm/chart.js', array(), '4.4.0', true);
            wp_enqueue_script('eve-observer-dashboard', plugin_dir_url(__FILE__) . 'js/dashboard.js', array('chart-js'), '1.0.0', true);
        }
        
        // Add CSS for thumbnail column width
        wp_add_inline_style('wp-admin', '
            .column-thumbnail { width: 60px; text-align: center; }
            .column-thumbnail img { max-width: 50px; max-height: 50px; }
        ');
    }

    public function display_dashboard() {
        if (!current_user_can('manage_options')) {
            wp_die(__('You do not have sufficient permissions to access this page.'));
        }

        // Get data counts
        $character_count = wp_count_posts('eve_character')->publish;
        $blueprint_count = wp_count_posts('eve_blueprint')->publish;
        $planet_count = wp_count_posts('eve_planet')->publish;
        $corporation_count = wp_count_posts('eve_corporation')->publish;
        $contract_count = wp_count_posts('eve_contract')->publish;

        ?>
        <div class="eve-dashboard">
            <div class="eve-dashboard-header">
                <h1><?php _e('EVE Observer Dashboard', 'eve-observer'); ?></h1>
                <p><?php _e('Monitor your EVE Online assets and activities with real-time insights.', 'eve-observer'); ?></p>
            </div>

            <!-- Overview Cards -->
            <div class="eve-overview-grid">
                <div class="eve-card eve-card-clickable" data-section="characters">
                    <div class="eve-card-header">
                        <div class="eve-card-icon" style="background: rgba(0, 122, 255, 0.1); color: var(--primary-color);">👤</div>
                        <h3 class="eve-card-title"><?php _e('Characters', 'eve-observer'); ?></h3>
                    </div>
                    <p class="eve-card-value"><?php echo esc_html($character_count); ?></p>
                </div>

                <div class="eve-card eve-card-clickable" data-section="blueprints">
                    <div class="eve-card-header">
                        <div class="eve-card-icon" style="background: rgba(255, 149, 0, 0.1); color: var(--warning-color);">📋</div>
                        <h3 class="eve-card-title"><?php _e('Blueprints', 'eve-observer'); ?></h3>
                    </div>
                    <p class="eve-card-value"><?php echo esc_html($blueprint_count); ?></p>
                </div>

                <div class="eve-card eve-card-clickable" data-section="planets">
                    <div class="eve-card-header">
                        <div class="eve-card-icon" style="background: rgba(52, 199, 89, 0.1); color: var(--success-color);">🌍</div>
                        <h3 class="eve-card-title"><?php _e('Planets', 'eve-observer'); ?></h3>
                    </div>
                    <p class="eve-card-value"><?php echo esc_html($planet_count); ?></p>
                </div>

                <div class="eve-card eve-card-clickable" data-section="corporations">
                    <div class="eve-card-header">
                        <div class="eve-card-icon" style="background: rgba(255, 59, 48, 0.1); color: var(--danger-color);">🏢</div>
                        <h3 class="eve-card-title"><?php _e('Corporations', 'eve-observer'); ?></h3>
                    </div>
                    <p class="eve-card-value"><?php echo esc_html($corporation_count); ?></p>
                </div>

                <div class="eve-card eve-card-clickable" data-section="contracts">
                    <div class="eve-card-header">
                        <div class="eve-card-icon" style="background: rgba(142, 142, 147, 0.1); color: #8e8e93;">📄</div>
                        <h3 class="eve-card-title"><?php _e('Contracts', 'eve-observer'); ?></h3>
                    </div>
                    <p class="eve-card-value"><?php echo esc_html($contract_count); ?></p>
                </div>
            </div>

            <!-- Chart Section -->
            <div class="eve-chart-section">
                <div class="eve-chart-container">
                    <h2><?php _e('Asset Distribution', 'eve-observer'); ?></h2>
                    <div style="position: relative; height: 400px;">
                        <canvas id="eveChart"></canvas>
                    </div>
                </div>
            </div>

            <!-- Characters Section -->
            <div class="eve-data-section" id="characters-section">
                <h2><?php _e('Characters', 'eve-observer'); ?></h2>
                <div class="eve-loading" id="characters-loading">
                    <div class="eve-loading-spinner"></div>
                    <span>Loading characters...</span>
                </div>
                <div id="characters-content" style="display: none;">
                    <div class="eve-search-container">
                        <input type="text" class="eve-search-input" id="characters-search" placeholder="Search characters...">
                    </div>
                    <table class="eve-data-table" id="characters-table">
                        <thead>
                            <tr>
                                <th><?php _e('Name', 'eve-observer'); ?></th>
                                <th><?php _e('Corporation', 'eve-observer'); ?></th>
                                <th><?php _e('Alliance', 'eve-observer'); ?></th>
                                <th><?php _e('Security Status', 'eve-observer'); ?></th>
                                <th><?php _e('Location', 'eve-observer'); ?></th>
                            </tr>
                        </thead>
                        <tbody id="characters-tbody">
                            <!-- Characters will be loaded here -->
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Blueprints Section -->
            <div class="eve-data-section" id="blueprints-section">
                <h2><?php _e('Blueprints', 'eve-observer'); ?></h2>
                <div class="eve-loading" id="blueprints-loading">
                    <div class="eve-loading-spinner"></div>
                    <span>Loading blueprints...</span>
                </div>
                <div id="blueprints-content" style="display: none;">
                    <div class="eve-search-container">
                        <input type="text" class="eve-search-input" id="blueprints-search" placeholder="Search blueprints...">
                    </div>
                    <table class="eve-data-table" id="blueprints-table">
                        <thead>
                            <tr>
                                <th><?php _e('Name', 'eve-observer'); ?></th>
                                <th><?php _e('Type ID', 'eve-observer'); ?></th>
                                <th><?php _e('Location', 'eve-observer'); ?></th>
                                <th><?php _e('ME', 'eve-observer'); ?></th>
                                <th><?php _e('TE', 'eve-observer'); ?></th>
                                <th><?php _e('Runs', 'eve-observer'); ?></th>
                            </tr>
                        </thead>
                        <tbody id="blueprints-tbody">
                            <!-- Blueprints will be loaded here -->
                        </tbody>
                    </table>
                    <div class="eve-pagination" id="blueprints-pagination"></div>
                </div>
            </div>

            <!-- Planets Section -->
            <div class="eve-data-section" id="planets-section">
                <h2><?php _e('Planets', 'eve-observer'); ?></h2>
                <div class="eve-loading" id="planets-loading">
                    <div class="eve-loading-spinner"></div>
                    <span>Loading planets...</span>
                </div>
                <div id="planets-content" style="display: none;">
                    <div class="eve-search-container">
                        <input type="text" class="eve-search-input" id="planets-search" placeholder="Search planets...">
                    </div>
                    <table class="eve-data-table" id="planets-table">
                        <thead>
                            <tr>
                                <th><?php _e('Name', 'eve-observer'); ?></th>
                                <th><?php _e('Type', 'eve-observer'); ?></th>
                                <th><?php _e('Upgrade Level', 'eve-observer'); ?></th>
                                <th><?php _e('Solar System', 'eve-observer'); ?></th>
                                <th><?php _e('Active Pins', 'eve-observer'); ?></th>
                            </tr>
                        </thead>
                        <tbody id="planets-tbody">
                            <!-- Planets will be loaded here -->
                        </tbody>
                    </table>
                    <div class="eve-pagination" id="planets-pagination"></div>
                </div>
            </div>

            <!-- Corporations Section -->
            <div class="eve-data-section" id="corporations-section">
                <h2><?php _e('Corporations', 'eve-observer'); ?></h2>
                <div class="eve-loading" id="corporations-loading">
                    <div class="eve-loading-spinner"></div>
                    <span>Loading corporations...</span>
                </div>
                <div id="corporations-content" style="display: none;">
                    <div class="eve-search-container">
                        <input type="text" class="eve-search-input" id="corporations-search" placeholder="Search corporations...">
                    </div>
                    <table class="eve-data-table" id="corporations-table">
                        <thead>
                            <tr>
                                <th><?php _e('Name', 'eve-observer'); ?></th>
                                <th><?php _e('Ticker', 'eve-observer'); ?></th>
                                <th><?php _e('Member Count', 'eve-observer'); ?></th>
                                <th><?php _e('Tax Rate', 'eve-observer'); ?></th>
                                <th><?php _e('Wallet Balance', 'eve-observer'); ?></th>
                            </tr>
                        </thead>
                        <tbody id="corporations-tbody">
                            <!-- Corporations will be loaded here -->
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Contracts Section -->
            <div class="eve-data-section" id="contracts-section">
                <h2><?php _e('Contracts', 'eve-observer'); ?></h2>
                <div class="eve-loading" id="contracts-loading">
                    <div class="eve-loading-spinner"></div>
                    <span>Loading contracts...</span>
                </div>
                <div id="contracts-content" style="display: none;">
                    <div class="eve-section-actions">
                        <button id="copy-outbid-contracts" class="button button-secondary"><?php _e('Copy Outbid Contracts', 'eve-observer'); ?></button>
                    </div>
                    <div class="eve-search-container">
                        <input type="text" class="eve-search-input" id="contracts-search" placeholder="Search contracts...">
                    </div>
                    <table class="eve-data-table" id="contracts-table">
                        <thead>
                            <tr>
                                <th><?php _e('Title', 'eve-observer'); ?></th>
                                <th><?php _e('Type', 'eve-observer'); ?></th>
                                <th><?php _e('Status', 'eve-observer'); ?></th>
                                <th><?php _e('Price', 'eve-observer'); ?></th>
                                <th><?php _e('Issuer', 'eve-observer'); ?></th>
                                <th><?php _e('Outbid', 'eve-observer'); ?></th>
                            </tr>
                        </thead>
                        <tbody id="contracts-tbody">
                            <!-- Contracts will be loaded here -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        <?php
    }

    public function activate() {
        // Register CPTs on activation
        $this->register_custom_post_types();
        // Flush rewrite rules
        flush_rewrite_rules();
    }

    public function deactivate() {
        // Flush rewrite rules on deactivation
        flush_rewrite_rules();
    }

    private function register_custom_post_types() {
        // Character CPT
        register_post_type('eve_character', array(
            'labels' => array(
                'name' => __('Characters', 'eve-observer'),
                'singular_name' => __('Character', 'eve-observer'),
            ),
            'public' => true,
            'supports' => array('title', 'editor', 'custom-fields'),
            'show_in_rest' => true,
            'show_in_menu' => false,
        ));

        // Blueprint CPT
        register_post_type('eve_blueprint', array(
            'labels' => array(
                'name' => __('Blueprints', 'eve-observer'),
                'singular_name' => __('Blueprint', 'eve-observer'),
            ),
            'public' => true,
            'supports' => array('title', 'editor', 'custom-fields'),
            'show_in_rest' => true,
            'show_in_menu' => false,
        ));

        // Planet CPT
        register_post_type('eve_planet', array(
            'labels' => array(
                'name' => __('Planets', 'eve-observer'),
                'singular_name' => __('Planet', 'eve-observer'),
            ),
            'public' => true,
            'supports' => array('title', 'editor', 'custom-fields'),
            'show_in_rest' => true,
            'show_in_menu' => false,
        ));

        // Corporation CPT
        register_post_type('eve_corporation', array(
            'labels' => array(
                'name' => __('Corporations', 'eve-observer'),
                'singular_name' => __('Corporation', 'eve-observer'),
            ),
            'public' => true,
            'supports' => array('title', 'editor', 'custom-fields'),
            'show_in_rest' => true,
            'show_in_menu' => false,
        ));

        // Contract CPT
        register_post_type('eve_contract', array(
            'labels' => array(
                'name' => __('Contracts', 'eve-observer'),
                'singular_name' => __('Contract', 'eve-observer'),
            ),
            'public' => true,
            'supports' => array('title', 'editor', 'custom-fields'),
            'show_in_rest' => true,
            'show_in_menu' => false,
        ));

        // Register ACF field groups if ACF is active
        $this->register_acf_field_groups();
    }

    private function register_acf_field_groups() {
        if (!function_exists('acf_add_local_field_group')) {
            return;
        }

        // Character Fields
        acf_add_local_field_group(array(
            'key' => 'group_eve_character',
            'title' => 'Character Information',
            'fields' => array(
                array(
                    'key' => 'field_char_id',
                    'label' => 'Character ID',
                    'name' => '_eve_char_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_id',
                    'label' => 'Corporation ID',
                    'name' => '_eve_corporation_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_alliance_id',
                    'label' => 'Alliance ID',
                    'name' => '_eve_alliance_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_birthday',
                    'label' => 'Birthday',
                    'name' => '_eve_birthday',
                    'type' => 'date_time_picker',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_security_status',
                    'label' => 'Security Status',
                    'name' => '_eve_security_status',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_total_sp',
                    'label' => 'Total Skill Points',
                    'name' => '_eve_total_sp',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_wallet_balance',
                    'label' => 'Wallet Balance',
                    'name' => '_eve_wallet_balance',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_location_id',
                    'label' => 'Current Location ID',
                    'name' => '_eve_location_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_location_name',
                    'label' => 'Current Location Name',
                    'name' => '_eve_location_name',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_assets_data',
                    'label' => 'Assets Data (JSON)',
                    'name' => '_eve_assets_data',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_killmails_data',
                    'label' => 'Killmails Data (JSON)',
                    'name' => '_eve_killmails_data',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_clones_data',
                    'label' => 'Clones Data (JSON)',
                    'name' => '_eve_clones_data',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_implants_data',
                    'label' => 'Implants Data (JSON)',
                    'name' => '_eve_implants_data',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_standings_data',
                    'label' => 'Standings Data (JSON)',
                    'name' => '_eve_standings_data',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_thumbnail_external_url',
                    'label' => 'External Thumbnail URL',
                    'name' => '_thumbnail_external_url',
                    'type' => 'url',
                    'show_in_rest' => true,
                ),
            ),
            'location' => array(
                array(
                    array(
                        'param' => 'post_type',
                        'operator' => '==',
                        'value' => 'eve_character',
                    ),
                ),
            ),
        ));

        // Blueprint Fields
        acf_add_local_field_group(array(
            'key' => 'group_eve_blueprint',
            'title' => 'Blueprint Information',
            'fields' => array(
                array(
                    'key' => 'field_bp_item_id',
                    'label' => 'Item ID',
                    'name' => '_eve_bp_item_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_bp_type_id',
                    'label' => 'Type ID',
                    'name' => '_eve_bp_type_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_bp_location_id',
                    'label' => 'Location ID',
                    'name' => '_eve_bp_location_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_bp_location_name',
                    'label' => 'Location Name',
                    'name' => '_eve_bp_location_name',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_bp_quantity',
                    'label' => 'Quantity',
                    'name' => '_eve_bp_quantity',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_bp_me',
                    'label' => 'Material Efficiency',
                    'name' => '_eve_bp_me',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_bp_te',
                    'label' => 'Time Efficiency',
                    'name' => '_eve_bp_te',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_bp_runs',
                    'label' => 'Runs',
                    'name' => '_eve_bp_runs',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_bp_thumbnail_external_url',
                    'label' => 'External Thumbnail URL',
                    'name' => '_thumbnail_external_url',
                    'type' => 'url',
                    'show_in_rest' => true,
                ),
            ),
            'location' => array(
                array(
                    array(
                        'param' => 'post_type',
                        'operator' => '==',
                        'value' => 'eve_blueprint',
                    ),
                ),
            ),
        ));

        // Planet Fields
        acf_add_local_field_group(array(
            'key' => 'group_eve_planet',
            'title' => 'Planet Information',
            'fields' => array(
                array(
                    'key' => 'field_planet_id',
                    'label' => 'Planet ID',
                    'name' => '_eve_planet_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_planet_type',
                    'label' => 'Planet Type',
                    'name' => '_eve_planet_type',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_planet_solar_system_id',
                    'label' => 'Solar System ID',
                    'name' => '_eve_planet_solar_system_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_planet_upgrade_level',
                    'label' => 'Upgrade Level',
                    'name' => '_eve_planet_upgrade_level',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_planet_thumbnail_external_url',
                    'label' => 'External Thumbnail URL',
                    'name' => '_thumbnail_external_url',
                    'type' => 'url',
                    'show_in_rest' => true,
                ),
            ),
            'location' => array(
                array(
                    array(
                        'param' => 'post_type',
                        'operator' => '==',
                        'value' => 'eve_planet',
                    ),
                ),
            ),
        ));

        // Corporation Fields
        acf_add_local_field_group(array(
            'key' => 'group_eve_corporation',
            'title' => 'Corporation Information',
            'fields' => array(
                array(
                    'key' => 'field_corp_id',
                    'label' => 'Corporation ID',
                    'name' => '_eve_corp_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_name',
                    'label' => 'Corporation Name',
                    'name' => '_eve_corp_name',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_ticker',
                    'label' => 'Ticker',
                    'name' => '_eve_corp_ticker',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_member_count',
                    'label' => 'Member Count',
                    'name' => '_eve_corp_member_count',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_ceo_id',
                    'label' => 'CEO ID',
                    'name' => '_eve_corp_ceo_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_alliance_id',
                    'label' => 'Alliance ID',
                    'name' => '_eve_corp_alliance_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_tax_rate',
                    'label' => 'Tax Rate',
                    'name' => '_eve_corp_tax_rate',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_wallet_balance',
                    'label' => 'Wallet Balance',
                    'name' => '_eve_corp_wallet_balance',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_assets_data',
                    'label' => 'Assets Data (JSON)',
                    'name' => '_eve_corp_assets_data',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_blueprints_data',
                    'label' => 'Blueprints Data (JSON)',
                    'name' => '_eve_corp_blueprints_data',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_industry_jobs_data',
                    'label' => 'Industry Jobs Data (JSON)',
                    'name' => '_eve_corp_industry_jobs_data',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_orders_data',
                    'label' => 'Market Orders Data (JSON)',
                    'name' => '_eve_corp_orders_data',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_structures_data',
                    'label' => 'Structures Data (JSON)',
                    'name' => '_eve_corp_structures_data',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_corp_thumbnail_external_url',
                    'label' => 'External Thumbnail URL',
                    'name' => '_thumbnail_external_url',
                    'type' => 'url',
                    'show_in_rest' => true,
                ),
            ),
            'location' => array(
                array(
                    array(
                        'param' => 'post_type',
                        'operator' => '==',
                        'value' => 'eve_corporation',
                    ),
                ),
            ),
        ));

        // Contract Fields
        acf_add_local_field_group(array(
            'key' => 'group_eve_contract',
            'title' => 'Contract Information',
            'fields' => array(
                array(
                    'key' => 'field_contract_id',
                    'label' => 'Contract ID',
                    'name' => '_eve_contract_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_type',
                    'label' => 'Contract Type',
                    'name' => '_eve_contract_type',
                    'type' => 'select',
                    'choices' => array(
                        'item_exchange' => 'Item Exchange',
                        'auction' => 'Auction',
                        'courier' => 'Courier',
                        'loan' => 'Loan',
                    ),
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_status',
                    'label' => 'Status',
                    'name' => '_eve_contract_status',
                    'type' => 'select',
                    'choices' => array(
                        'outstanding' => 'Outstanding',
                        'in_progress' => 'In Progress',
                        'finished_issuer' => 'Finished (Issuer)',
                        'finished_contractor' => 'Finished (Contractor)',
                        'finished' => 'Finished',
                        'cancelled' => 'Cancelled',
                        'rejected' => 'Rejected',
                        'failed' => 'Failed',
                        'deleted' => 'Deleted',
                        'reversed' => 'Reversed',
                    ),
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_title',
                    'label' => 'Title',
                    'name' => '_eve_contract_title',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_for_corp',
                    'label' => 'For Corporation',
                    'name' => '_eve_contract_for_corp',
                    'type' => 'true_false',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_issuer_id',
                    'label' => 'Issuer ID',
                    'name' => '_eve_contract_issuer_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_issuer_corp_id',
                    'label' => 'Issuer Corporation ID',
                    'name' => '_eve_contract_issuer_corp_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_assignee_id',
                    'label' => 'Assignee ID',
                    'name' => '_eve_contract_assignee_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_acceptor_id',
                    'label' => 'Acceptor ID',
                    'name' => '_eve_contract_acceptor_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_start_location_id',
                    'label' => 'Start Location ID',
                    'name' => '_eve_contract_start_location_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_end_location_id',
                    'label' => 'End Location ID',
                    'name' => '_eve_contract_end_location_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_date_issued',
                    'label' => 'Date Issued',
                    'name' => '_eve_contract_date_issued',
                    'type' => 'date_time_picker',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_date_expired',
                    'label' => 'Date Expired',
                    'name' => '_eve_contract_date_expired',
                    'type' => 'date_time_picker',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_date_accepted',
                    'label' => 'Date Accepted',
                    'name' => '_eve_contract_date_accepted',
                    'type' => 'date_time_picker',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_date_completed',
                    'label' => 'Date Completed',
                    'name' => '_eve_contract_date_completed',
                    'type' => 'date_time_picker',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_price',
                    'label' => 'Price',
                    'name' => '_eve_contract_price',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_reward',
                    'label' => 'Reward',
                    'name' => '_eve_contract_reward',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_collateral',
                    'label' => 'Collateral',
                    'name' => '_eve_contract_collateral',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_buyout',
                    'label' => 'Buyout',
                    'name' => '_eve_contract_buyout',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_days_to_complete',
                    'label' => 'Days to Complete',
                    'name' => '_eve_contract_days_to_complete',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_entity_id',
                    'label' => 'Entity ID',
                    'name' => '_eve_contract_entity_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_outbid',
                    'label' => 'Outbid',
                    'name' => '_eve_contract_outbid',
                    'type' => 'true_false',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_market_price',
                    'label' => 'Market Price',
                    'name' => '_eve_contract_market_price',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_region_id',
                    'label' => 'Region ID',
                    'name' => '_eve_contract_region_id',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_items',
                    'label' => 'Contract Items (JSON)',
                    'name' => '_eve_contract_items',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
            ),
    }

    public function get_post_thumbnail_id_external($thumbnail_id, $post_id = null) {
        if (get_post_meta($post_id, '_thumbnail_external_url', true)) {
            // Return a dummy ID to indicate external image exists
            return 'external';
        }
        
        return $thumbnail_id;
    }

    public function post_thumbnail_external_url($html, $post_id, $post_thumbnail_id, $size, $attr) {
        // Check if this is an external image (our dummy ID)
        if ($post_thumbnail_id === 'external') {
            $external_url = get_post_meta($post_id, '_thumbnail_external_url', true);
            
            if (!empty($external_url)) {
                $alt = get_the_title($post_id);
                $class = isset($attr['class']) ? $attr['class'] : 'wp-post-image';
                $width = isset($attr['width']) ? $attr['width'] : '';
                $height = isset($attr['height']) ? $attr['height'] : '';
                
                $html = sprintf(
                    '<img src="%s" alt="%s" class="%s" width="%s" height="%s" />',
                    esc_url($external_url),
                    esc_attr($alt),
                    esc_attr($class),
                    esc_attr($width),
                    esc_attr($height)
                );
            }
        }
        
        return $html;
    }

    public function add_thumbnail_column($columns) {
        $new_columns = array();
        
        // Insert thumbnail column before title
        foreach ($columns as $key => $value) {
            if ($key === 'title') {
                $new_columns['thumbnail'] = __('Thumbnail', 'eve-observer');
            }
            $new_columns[$key] = $value;
        }
        
        return $new_columns;
    }

    public function display_thumbnail_column($column, $post_id) {
        if ($column === 'thumbnail') {
            $thumbnail_url = get_post_meta($post_id, '_thumbnail_external_url', true);
            
            if (!empty($thumbnail_url)) {
                echo '<img src="' . esc_url($thumbnail_url) . '" alt="' . esc_attr(get_the_title($post_id)) . '" style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px;" />';
            } else {
                echo '<div style="width: 50px; height: 50px; background: #f0f0f0; border: 1px solid #ddd; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: #999; font-size: 20px;">📷</div>';
            }
        }
    }

    public function add_outbid_column($columns) {
        $new_columns = array();
        
        // Insert outbid column after title
        foreach ($columns as $key => $value) {
            $new_columns[$key] = $value;
            if ($key === 'title') {
                $new_columns['outbid'] = __('Outbid', 'eve-observer');
            }
        }
        
        return $new_columns;
    }

    public function display_outbid_column($column, $post_id) {
        if ($column === 'outbid') {
            $is_outbid = get_post_meta($post_id, '_eve_contract_outbid', true) === '1';
            $contract_id = get_post_meta($post_id, '_eve_contract_id', true);
            $contract_title = get_post_meta($post_id, '_eve_contract_title', true);
            $start_location_id = get_post_meta($post_id, '_eve_contract_start_location_id', true);
            $market_price = get_post_meta($post_id, '_eve_contract_market_price', true);
            
            if ($is_outbid) {
                $status_text = 'Outbid';
                $color = '#dc3545'; // Red
                $icon = '⚠️';
            } else {
                $status_text = 'OK';
                $color = '#28a745'; // Green
                $icon = '✅';
            }
            
            // Build EVE chat link for clipboard copying
            $eve_link = '';
            $link_title = !empty($contract_title) ? esc_html($contract_title) : 'Contract';
            if (!empty($contract_id)) {
                $location_id = $start_location_id;
                if (empty($location_id)) {
                    $location_id = get_post_meta($post_id, '_eve_contract_end_location_id', true);
                }
                if (!empty($location_id)) {
                    $eve_link = '<a href="contract:' . $location_id . '//' . $contract_id . '">' . $link_title . '</a>';
                } else {
                    // Fallback: create link without location (might still work in some cases)
                    $eve_link = '<a href="contract://' . $contract_id . '">' . $link_title . '</a>';
                }
            }
            
            echo "<div style='display: flex; align-items: center; gap: 8px;'>";
            
            // Make status always clickable for clipboard copy if we have contract data
            if (!empty($eve_link)) {
                echo "<span style='color: " . esc_attr($color) . "; font-weight: bold; cursor: pointer;' onclick='copyToClipboard(" . json_encode($eve_link) . ")' title='Click to copy EVE chat link'>" . esc_html($icon . ' ' . $status_text) . "</span>";
            } elseif (!empty($contract_id)) {
                // Fallback: copy just the contract ID if we can't make a proper link
                echo "<span style='color: " . esc_attr($color) . "; font-weight: bold; cursor: pointer;' onclick='copyToClipboard(" . json_encode($contract_id) . ")' title='Click to copy contract ID'>" . esc_html($icon . ' ' . $status_text) . "</span>";
            } else {
                echo "<span style='color: " . esc_attr($color) . "; font-weight: bold;'>" . esc_html($icon . ' ' . $status_text) . "</span>";
            }
            
            if ($is_outbid && !empty($market_price) && is_numeric($market_price)) {
                $formatted_price = number_format((float)$market_price, 2);
                echo "<span style='color: #666; font-size: 12px; cursor: pointer;' onclick='copyToClipboard(" . json_encode($formatted_price) . ")' title='Click to copy suggested price'>Suggested: " . esc_html($formatted_price) . " ISK</span>";
            }
            
            echo "</div>";
        }
    }

    public function make_outbid_column_sortable($columns) {
        $columns['outbid'] = 'outbid';
        return $columns;
    }

    public function sort_outbid_column($query) {
        if (!is_admin() || !$query->is_main_query()) {
            return;
        }
        
        if ($query->get('orderby') === 'outbid') {
            $query->set('meta_key', '_eve_contract_outbid');
            $query->set('orderby', 'meta_value_num');
            // ACF true_false stores '1' for true, '0' for false
            // In DESC order: '1' (outbid) comes before '0' (not outbid)
        }
    }
}

// Initialize the plugin
new EVE_Observer();