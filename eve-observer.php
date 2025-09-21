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
            '_eve_ancestry_id', '_eve_security_status', '_eve_last_updated'
        );
        $numeric_char_fields = array('_eve_char_id', '_eve_corporation_id', '_eve_alliance_id', '_eve_race_id', '_eve_bloodline_id', '_eve_ancestry_id', '_eve_security_status');
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
            '_eve_bp_me', '_eve_bp_te', '_eve_bp_runs', '_eve_char_id', '_eve_last_updated'
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
    }

    public function enqueue_admin_scripts($hook) {
        if ($hook !== 'toplevel_page_eve-observer-dashboard') {
            return;
        }
        wp_enqueue_script('chart-js', 'https://cdn.jsdelivr.net/npm/chart.js', array(), '4.4.0', true);
        wp_enqueue_script('eve-observer-dashboard', plugin_dir_url(__FILE__) . 'js/dashboard.js', array('chart-js'), '1.0.0', true);
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
    }
}

// Initialize the plugin
new EVE_Observer();