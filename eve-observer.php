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
        register_activation_hook(__FILE__, array($this, 'activate'));
        register_deactivation_hook(__FILE__, array($this, 'deactivate'));
    }

    public function init() {
        // Register custom post types
        $this->register_custom_post_types();
    }

    public function add_admin_menu() {
        add_menu_page(
            __('EVE Observer Dashboard', 'eve-observer'),
            __('EVE Observer', 'eve-observer'),
            'manage_options',
            'eve-observer-dashboard',
            array($this, 'display_dashboard'),
            'dashicons-chart-area',
            30
        );
    }

    public function display_dashboard() {
        if (!current_user_can('manage_options')) {
            wp_die(__('You do not have sufficient permissions to access this page.'));
        }
        ?>
        <div class="wrap">
            <h1><?php _e('EVE Observer Dashboard', 'eve-observer'); ?></h1>
            <p><?php _e('Welcome to the EVE Observer dashboard. Here you can view aggregated data from your EVE Online characters.', 'eve-observer'); ?></p>
            <!-- Placeholder for character data -->
            <h2><?php _e('Characters', 'eve-observer'); ?></h2>
            <p><?php _e('Character data will be displayed here once integrated with ESI API.', 'eve-observer'); ?></p>
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
}

// Initialize the plugin
new EVE_Observer();