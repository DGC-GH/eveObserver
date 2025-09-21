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
            '_eve_contract_outbid', '_eve_contract_market_price'
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
        if ($hook !== 'toplevel_page_eve-observer-dashboard') {
            return;
        }
        wp_enqueue_script('chart-js', 'https://cdn.jsdelivr.net/npm/chart.js', array(), '4.4.0', true);
        wp_enqueue_script('eve-observer-dashboard', plugin_dir_url(__FILE__) . 'js/dashboard.js', array('chart-js'), '1.0.0', true);
        
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
        ?>
        <div class="wrap">
            <h1><?php _e('EVE Observer Dashboard', 'eve-observer'); ?></h1>
            <p><?php _e('Welcome to the EVE Observer dashboard. Here you can view aggregated data from your EVE Online characters.', 'eve-observer'); ?></p>

            <!-- Chart Container -->
            <div style="width: 80%; margin: 20px auto;">
                <canvas id="eveChart"></canvas>
            </div>

            <!-- Characters -->
            <h2><?php _e('Characters', 'eve-observer'); ?></h2>
            <?php
            $characters = get_posts(array('post_type' => 'eve_character', 'numberposts' => -1));
            if ($characters) {
                echo '<ul>';
                foreach ($characters as $char) {
                    $char_id = get_post_meta($char->ID, '_eve_char_id', true);
                    $corp_id = get_post_meta($char->ID, '_eve_corporation_id', true);
                    echo '<li>' . esc_html($char->post_title) . ' (ID: ' . esc_html($char_id) . ', Corp: ' . esc_html($corp_id) . ')</li>';
                }
                echo '</ul>';
            } else {
                echo '<p>No character data available.</p>';
            }
            ?>

            <!-- Blueprints -->
            <h2><?php _e('Blueprints', 'eve-observer'); ?></h2>
            <?php
            $blueprints = get_posts(array('post_type' => 'eve_blueprint', 'numberposts' => -1));
            if ($blueprints) {
                echo '<p>Total Blueprints: ' . count($blueprints) . '</p>';
                echo '<ul>';
                foreach ($blueprints as $bp) {
                    $type_id = get_post_meta($bp->ID, '_eve_bp_type_id', true);
                    $me = get_post_meta($bp->ID, '_eve_bp_me', true);
                    $te = get_post_meta($bp->ID, '_eve_bp_te', true);
                    echo '<li>Blueprint ' . esc_html($type_id) . ' (ME: ' . esc_html($me) . ', TE: ' . esc_html($te) . ')</li>';
                }
                echo '</ul>';
            } else {
                echo '<p>No blueprint data available.</p>';
            }
            ?>

            <!-- Planets -->
            <h2><?php _e('Planets', 'eve-observer'); ?></h2>
            <?php
            $planets = get_posts(array('post_type' => 'eve_planet', 'numberposts' => -1));
            if ($planets) {
                echo '<p>Total Planets: ' . count($planets) . '</p>';
                echo '<ul>';
                foreach ($planets as $planet) {
                    $planet_type = get_post_meta($planet->ID, '_eve_planet_type', true);
                    echo '<li>' . esc_html($planet->post_title) . ' (Type: ' . esc_html($planet_type) . ')</li>';
                }
                echo '</ul>';
            } else {
                echo '<p>No planet data available.</p>';
            }
            ?>

            <!-- Corporations -->
            <h2><?php _e('Corporations', 'eve-observer'); ?></h2>
            <?php
            $corporations = get_posts(array('post_type' => 'eve_corporation', 'numberposts' => -1));
            if ($corporations) {
                echo '<p>Total Corporations: ' . count($corporations) . '</p>';
                echo '<ul>';
                foreach ($corporations as $corp) {
                    $corp_id = get_post_meta($corp->ID, '_eve_corp_id', true);
                    $ticker = get_post_meta($corp->ID, '_eve_corp_ticker', true);
                    echo '<li>' . esc_html($corp->post_title) . ' [' . esc_html($ticker) . '] (ID: ' . esc_html($corp_id) . ')</li>';
                }
                echo '</ul>';
            } else {
                echo '<p>No corporation data available.</p>';
            }
            ?>

            <!-- Contracts -->
            <h2><?php _e('Contracts', 'eve-observer'); ?></h2>
            <?php
            $contracts = get_posts(array('post_type' => 'eve_contract', 'numberposts' => -1));
            if ($contracts) {
                echo '<p>Total Contracts: ' . count($contracts) . '</p>';
                echo '<ul>';
                foreach ($contracts as $contract) {
                    $contract_id = get_post_meta($contract->ID, '_eve_contract_id', true);
                    $type = get_post_meta($contract->ID, '_eve_contract_type', true);
                    $status = get_post_meta($contract->ID, '_eve_contract_status', true);
                    echo '<li>' . esc_html($contract->post_title) . ' (' . esc_html($type) . ' - ' . esc_html($status) . ') (ID: ' . esc_html($contract_id) . ')</li>';
                }
                echo '</ul>';
            } else {
                echo '<p>No contract data available.</p>';
            }
            ?>
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
                    'key' => 'field_contract_items',
                    'label' => 'Contract Items (JSON)',
                    'name' => '_eve_contract_items',
                    'type' => 'textarea',
                    'show_in_rest' => true,
                ),
            ),
            'location' => array(
                array(
                    array(
                        'param' => 'post_type',
                        'operator' => '==',
                        'value' => 'eve_contract',
                    ),
                ),
            ),
        ));
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
            $is_outbid = get_post_meta($post_id, '_eve_contract_outbid', true) === 'true';
            $contract_id = get_post_meta($post_id, '_eve_contract_id', true);
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
            
            // Make contract ID clickable to open in EVE client
            $eve_client_url = "eve://app/contract/{$contract_id}";
            $clickable_id = "<a href='" . esc_url($eve_client_url) . "' target='_blank' style='color: #0073aa; text-decoration: none;' title='Open in EVE Client'>" . esc_html($contract_id) . "</a>";
            
            echo "<div style='display: flex; align-items: center; gap: 8px;'>";
            echo "<span style='color: " . esc_attr($color) . "; font-weight: bold;'>" . esc_html($icon . ' ' . $status_text) . "</span>";
            if ($is_outbid && !empty($market_price) && is_numeric($market_price)) {
                $formatted_price = number_format((float)$market_price, 2);
                echo "<span style='color: #666; font-size: 12px;'>Market: " . esc_html($formatted_price) . " ISK</span>";
            }
            echo "<span style='color: #666; font-size: 12px;'>ID: " . $clickable_id . "</span>";
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
            $query->set('orderby', 'meta_value');
            // Sort 'true' before 'false' (outbid contracts first)
            $query->set('meta_type', 'CHAR');
        }
    }
}

// Initialize the plugin
new EVE_Observer();