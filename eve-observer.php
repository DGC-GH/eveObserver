<?php
/**
 * Plugin Name: EVE Observer
 * Plugin URI: https://github.com/DGC-GH/eveObserver
 * Description: A custom WordPress plugin for EVE Online dashboard with ESI API integration.
 * Version: 1.2.0
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
        // Log plugin initialization
        error_log("🔄 [PLUGIN INIT] EVE Observer plugin constructor called");

        // Hook into WordPress
        add_action('init', array($this, 'init'));
        add_action('admin_menu', array($this, 'add_admin_menu'));
        add_action('admin_enqueue_scripts', array($this, 'enqueue_admin_scripts'));
        add_action('wp_ajax_eve_sync', array($this, 'handle_ajax_sync_request'));
        add_action('wp_ajax_eve_stop_sync', array($this, 'handle_ajax_stop_sync_request'));
        add_action('wp_ajax_eve_sync_status', array($this, 'handle_ajax_sync_status_request'));
        add_action('wp_ajax_eve_get_logs', array($this, 'handle_ajax_get_logs_request'));
        add_action('wp_ajax_eve_clear_logs', array($this, 'handle_ajax_clear_logs_request'));

        error_log("🔄 [PLUGIN INIT] AJAX action 'wp_ajax_eve_sync' registered");
        error_log("🔄 [PLUGIN INIT] AJAX action 'wp_ajax_eve_stop_sync' registered");
        error_log("🔄 [PLUGIN INIT] AJAX action 'wp_ajax_eve_sync_status' registered");
        error_log("🔄 [PLUGIN INIT] AJAX action 'wp_ajax_eve_get_logs' registered");
        error_log("🔄 [PLUGIN INIT] AJAX action 'wp_ajax_eve_clear_logs' registered");

        register_activation_hook(__FILE__, array($this, 'activate'));
        register_deactivation_hook(__FILE__, array($this, 'deactivate'));

        error_log("🔄 [PLUGIN INIT] EVE Observer plugin constructor completed");
    }

    public function init() {
        error_log("🔄 [PLUGIN INIT] EVE Observer init() method called");

        // Register meta for REST API
        register_meta('post', '_eve_planet_pins_data', array(
            'show_in_rest' => true,
            'single' => true,
            'type' => 'string',
            'auth_callback' => '__return_true'
        ));

        error_log("🔄 [PLUGIN INIT] Meta field _eve_planet_pins_data registered");

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
            '_eve_contract_for_corporation', '_eve_contract_availability', '_eve_contract_issuer_id', '_eve_contract_issuer_name',
            '_eve_contract_issuer_corporation_id', '_eve_contract_issuer_corporation_name', '_eve_contract_assignee_id', '_eve_contract_assignee_name',
            '_eve_contract_location_id', '_eve_contract_location_name', '_eve_contract_region_id', '_eve_contract_date_issued',
            '_eve_contract_date_expired', '_eve_contract_date_accepted', '_eve_contract_date_completed',
            '_eve_contract_price', '_eve_contract_reward', '_eve_contract_collateral', '_eve_contract_buyout',
            '_eve_contract_volume', '_eve_contract_days_to_complete', '_eve_contract_items', '_eve_last_updated',
            '_eve_contract_outbid', '_eve_contract_market_price', '_eve_contract_competing_price'
        );
        $numeric_contract_fields = array('_eve_contract_id', '_eve_contract_issuer_id', '_eve_contract_issuer_corporation_id', '_eve_contract_assignee_id', '_eve_contract_price', '_eve_contract_reward', '_eve_contract_collateral', '_eve_contract_buyout', '_eve_contract_volume', '_eve_contract_days_to_complete', '_eve_contract_market_price', '_eve_contract_competing_price');
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

        // Register REST API routes
        add_action('rest_api_init', array($this, 'register_rest_routes'));

        // Register custom post types
        $this->register_custom_post_types();
    }

    public function register_rest_routes() {
        register_rest_route('eve-observer/v1', '/sync/(?P<section>[a-zA-Z_]+)', array(
            'methods' => 'POST',
            'callback' => array($this, 'handle_sync_request'),
            'permission_callback' => array($this, 'check_sync_permissions'),
            'args' => array(
                'section' => array(
                    'required' => true,
                    'validate_callback' => function($param) {
                        return in_array($param, array('characters', 'blueprints', 'planets', 'corporations', 'contracts', 'all'));
                    }
                )
            )
        ));

        // Add test endpoint
        register_rest_route('eve-observer/v1', '/test', array(
            'methods' => 'GET',
            'callback' => array($this, 'handle_test_request'),
            'permission_callback' => array($this, 'check_sync_permissions')
        ));

        // Add sync status endpoint
        register_rest_route('eve-observer/v1', '/sync-status', array(
            'methods' => 'GET',
            'callback' => array($this, 'handle_sync_status_request'),
            'permission_callback' => array($this, 'check_sync_permissions')
        ));

        // Add stop sync endpoint
        register_rest_route('eve-observer/v1', '/stop-sync', array(
            'methods' => 'POST',
            'callback' => array($this, 'handle_stop_sync_request'),
            'permission_callback' => array($this, 'check_sync_permissions')
        ));

        error_log("🔄 [PLUGIN INIT] REST API routes registered");
    }

    public function check_sync_permissions() {
        return current_user_can('manage_options');
    }

    public function handle_test_request() {
        error_log("🔄 [TEST ENDPOINT] Test endpoint called");

        $response = array(
            'success' => true,
            'message' => 'EVE Observer test endpoint working',
            'timestamp' => current_time('mysql'),
            'php_version' => phpversion(),
            'shell_exec_available' => function_exists('shell_exec'),
            'plugin_dir' => plugin_dir_path(__FILE__),
            'scripts_dir_exists' => is_dir(plugin_dir_path(__FILE__) . 'scripts/')
        );

        // Test basic shell command
        if (function_exists('shell_exec')) {
            $test_command = 'echo "Shell exec test successful"';
            $shell_output = shell_exec($test_command);
            $response['shell_exec_test'] = trim($shell_output);
            error_log("🔄 [TEST ENDPOINT] Shell exec test result: " . $response['shell_exec_test']);
        }

        error_log("🔄 [TEST ENDPOINT] Test response: " . print_r($response, true));

        return $response;
    }

    public function handle_sync_status_request() {
        $scripts_dir = plugin_dir_path(__FILE__) . 'scripts/';
        $status_file = $scripts_dir . 'sync_status.json';

        if (!file_exists($status_file)) {
            return array(
                'running' => false,
                'message' => 'No sync in progress'
            );
        }

        $status_data = json_decode(file_get_contents($status_file), true);
        if (!$status_data) {
            return array(
                'running' => false,
                'message' => 'Invalid status data'
            );
        }

        // Check if the process is still running
        $pid = $status_data['pid'] ?? null;
        if ($pid && function_exists('posix_kill')) {
            // On Unix systems, check if process exists
            $running = posix_kill($pid, 0);
        } elseif ($pid && function_exists('shell_exec')) {
            // Fallback: check process list
            $process_check = shell_exec("ps -p $pid 2>/dev/null | grep $pid");
            $running = !empty($process_check);
        } else {
            // Fallback: assume running if file exists and is recent
            $timestamp = strtotime($status_data['timestamp'] ?? 'now');
            $age_seconds = time() - $timestamp;
            $running = $age_seconds < 3600; // Consider running if less than 1 hour old
        }

        if (!$running) {
            // Clean up stale status file
            @unlink($status_file);
            return array(
                'running' => false,
                'message' => 'No sync in progress'
            );
        }

        return array(
            'running' => true,
            'status' => $status_data['status'] ?? 'unknown',
            'progress' => $status_data['progress'] ?? 0.0,
            'message' => $status_data['message'] ?? '',
            'section' => $status_data['section'] ?? '',
            'timestamp' => $status_data['timestamp'] ?? '',
            'start_time' => $status_data['start_time'] ?? '',
            'pid' => $pid,
            'stages' => $status_data['stages'] ?? null
        );
    }

    public function handle_stop_sync_request() {
        error_log("🔄 [STOP SYNC] Stop sync request received");

        $scripts_dir = plugin_dir_path(__FILE__) . 'scripts/';
        $status_file = $scripts_dir . 'sync_status.json';
        $pid_file = $scripts_dir . 'main.pid';

        if (!file_exists($status_file)) {
            error_log("🔄 [STOP SYNC] No status file found");
            return new WP_Error('no_sync_running', 'No sync is currently running', array('status' => 400));
        }

        $status_data = json_decode(file_get_contents($status_file), true);
        $pid = $status_data['pid'] ?? null;

        if (!$pid) {
            error_log("🔄 [STOP SYNC] No PID in status file");
            @unlink($status_file);
            return new WP_Error('no_pid', 'No process ID found', array('status' => 400));
        }

        // Try to kill the process
        $killed = false;
        if (function_exists('posix_kill')) {
            $killed = posix_kill($pid, SIGTERM);
            error_log("🔄 [STOP SYNC] Sent SIGTERM to PID $pid: " . ($killed ? 'success' : 'failed'));
        } elseif (function_exists('shell_exec')) {
            // Fallback: use kill command
            $kill_output = shell_exec("kill $pid 2>/dev/null");
            $killed = true; // Assume success
            error_log("🔄 [STOP SYNC] Used kill command on PID $pid");
        }

        if ($killed) {
            // Clean up files
            @unlink($status_file);
            @unlink($pid_file);
            error_log("🔄 [STOP SYNC] Successfully stopped sync process $pid");

            return array(
                'success' => true,
                'message' => 'Sync process stopped successfully',
                'pid' => $pid
            );
        } else {
            error_log("🔄 [STOP SYNC] Failed to stop sync process $pid");
            return new WP_Error('stop_failed', 'Failed to stop sync process', array('status' => 500));
        }
    }

    public function handle_ajax_sync_status_request() {
        // Check permissions
        if (!current_user_can('manage_options')) {
            wp_die(__('You do not have sufficient permissions to access this page.'));
        }

        if (!wp_verify_nonce($_POST['nonce'], 'eve_sync_nonce')) {
            wp_send_json_error(array('message' => 'Security check failed'), 403);
            return;
        }

        // Call the main sync status handler
        $status = $this->handle_sync_status_request();
        wp_send_json_success($status);
    }

    public function handle_ajax_stop_sync_request() {
        // Log the start of AJAX request processing
        error_log("🔄 [AJAX STOP SYNC START] ========================================");
        error_log("🔄 [AJAX STOP SYNC START] handle_ajax_stop_sync_request called");
        error_log("🔄 [AJAX STOP SYNC START] Timestamp: " . current_time('mysql'));
        error_log("🔄 [AJAX STOP SYNC START] REQUEST_METHOD: " . ($_SERVER['REQUEST_METHOD'] ?? 'unknown'));
        error_log("🔄 [AJAX STOP SYNC START] POST data: " . print_r($_POST, true));
        error_log("🔄 [AJAX STOP SYNC START] GET data: " . print_r($_GET, true));
        error_log("🔄 [AJAX STOP SYNC START] Current user ID: " . get_current_user_id());
        error_log("🔄 [AJAX STOP SYNC START] Current user capabilities: " . print_r(wp_get_current_user()->allcaps, true));
        error_log("🔄 [AJAX STOP SYNC START] ========================================");

        // Check permissions
        if (!current_user_can('manage_options')) {
            error_log("❌ [AJAX STOP SYNC ERROR] User does not have manage_options capability");
            wp_die(__('You do not have sufficient permissions to access this page.'));
        }
        error_log("✅ [AJAX STOP SYNC STEP 1] User has manage_options capability");

        // Verify nonce
        if (!wp_verify_nonce($_POST['nonce'], 'eve_sync_nonce')) {
            error_log("❌ [AJAX STOP SYNC ERROR] Nonce verification failed");
            error_log("🔄 [AJAX STOP SYNC DEBUG] Received nonce: " . ($_POST['nonce'] ?? 'none'));
            error_log("🔄 [AJAX STOP SYNC DEBUG] Expected nonce action: eve_sync_nonce");
            wp_send_json_error(array('message' => 'Security check failed'), 403);
            return;
        }
        error_log("✅ [AJAX STOP SYNC STEP 2] Nonce verification passed");

        // Call the main stop sync handler
        $result = $this->handle_stop_sync_request();

        if (is_wp_error($result)) {
            error_log("❌ [AJAX STOP SYNC ERROR] Stop sync failed: " . $result->get_error_message());
            wp_send_json_error(array('message' => $result->get_error_message()), $result->get_error_data()['status'] ?? 500);
        } else {
            error_log("✅ [AJAX STOP SYNC SUCCESS] Stop sync completed successfully");
            wp_send_json_success($result);
        }
    }

    public function handle_ajax_sync_request() {
        // Quick permission and nonce check
        if (!current_user_can('manage_options')) {
            wp_die(__('You do not have sufficient permissions to access this page.'));
        }

        if (!wp_verify_nonce($_POST['nonce'], 'eve_sync_nonce')) {
            wp_send_json_error(array('message' => 'Security check failed'), 403);
            return;
        }

        $section = isset($_POST['section']) ? sanitize_text_field($_POST['section']) : 'all';

        // Check if a sync is already running
        $sync_status = $this->handle_sync_status_request();
        if ($sync_status['running']) {
            wp_send_json_error(array(
                'message' => 'A sync is already running. Would you like to stop it first?',
                'sync_running' => true,
                'current_status' => $sync_status
            ), 409);
            return;
        }

        // Map sections to Python scripts
        $script_map = array(
            'characters' => 'main.py --characters',
            'blueprints' => 'main.py --blueprints',
            'planets' => 'main.py --planets',
            'corporations' => 'main.py --corporations',
            'contracts' => 'main.py --contracts',
            'all' => 'main.py --all'
        );

        if (!isset($script_map[$section])) {
            wp_send_json_error(array('message' => 'Invalid section specified'), 400);
            return;
        }

        // Get plugin directory and create initial status file
        $plugin_dir = plugin_dir_path(__FILE__);
        $scripts_dir = $plugin_dir . 'scripts/';
        $status_file = $scripts_dir . 'sync_status.json';

        // Create initial status file immediately
        $initial_status = array(
            'running' => true,
            'section' => $section,
            'progress' => 0,
            'message' => 'Starting sync...',
            'stages' => array(
                'initialization' => array('status' => 'running', 'progress' => 0, 'message' => 'Initializing...'),
                'collection' => array('status' => 'pending', 'progress' => 0, 'message' => 'Preparing...'),
                'processing' => array('status' => 'pending', 'progress' => 0, 'message' => 'Preparing...'),
                'finalization' => array('status' => 'pending', 'progress' => 0, 'message' => 'Preparing...')
            ),
            'start_time' => time(),
            'pid' => 0
        );

        file_put_contents($status_file, json_encode($initial_status));

        // Simplified Python detection - try common paths quickly
        $python_cmd = '';
        $python_paths = array('/usr/bin/python3', '/usr/local/bin/python3', 'python3', 'python');

        foreach ($python_paths as $path) {
            if (file_exists($path) && is_executable($path)) {
                $python_cmd = $path;
                break;
            }
        }

        if (empty($python_cmd)) {
            // Fallback: try to find any python3 in /usr/bin or /usr/local/bin
            $python_cmd = trim(shell_exec('find /usr/bin /usr/local/bin -name "python3" -executable 2>/dev/null | head -1') ?: '');
            if (empty($python_cmd)) {
                $python_cmd = 'python3'; // Last resort
            }
        }

        // Build and execute command
        $script_parts = explode(' ', $script_map[$section], 2);
        $script_name = $script_parts[0];
        $script_args = isset($script_parts[1]) ? $script_parts[1] : '';

        $command_parts = array(
            'cd', escapeshellarg($scripts_dir), '&&',
            escapeshellarg($python_cmd),
            escapeshellarg($script_name)
        );

        if (!empty($script_args)) {
            $args_array = explode(' ', $script_args);
            foreach ($args_array as $arg) {
                $command_parts[] = escapeshellarg($arg);
            }
        }

        $command = implode(' ', $command_parts) . ' > /dev/null 2>&1 & echo $!';

        // Execute in background and get PID
        $pid = exec($command);

        if ($pid) {
            // Update status file with PID
            $initial_status['pid'] = $pid;
            file_put_contents($status_file, json_encode($initial_status));

            wp_send_json_success(array(
                'message' => 'Sync started successfully in background',
                'pid' => $pid,
                'status' => 'running'
            ));
        } else {
            // Clean up status file on failure
            if (file_exists($status_file)) {
                unlink($status_file);
            }

            wp_send_json_error(array('message' => 'Failed to start sync process'), 500);
        }
    }

    public function handle_ajax_get_logs_request() {
        // Log the start of AJAX request processing
        error_log("🔄 [AJAX LOGS START] ========================================");
        error_log("🔄 [AJAX LOGS START] handle_ajax_get_logs_request called");
        error_log("🔄 [AJAX LOGS START] Timestamp: " . current_time('mysql'));
        error_log("🔄 [AJAX LOGS START] REQUEST_METHOD: " . ($_SERVER['REQUEST_METHOD'] ?? 'unknown'));
        error_log("🔄 [AJAX LOGS START] POST data: " . print_r($_POST, true));
        error_log("🔄 [AJAX LOGS START] GET data: " . print_r($_GET, true));
        error_log("🔄 [AJAX LOGS START] Current user ID: " . get_current_user_id());
        error_log("🔄 [AJAX LOGS START] Current user capabilities: " . print_r(wp_get_current_user()->allcaps, true));
        error_log("🔄 [AJAX LOGS START] ========================================");

        // Check permissions
        if (!current_user_can('manage_options')) {
            error_log("❌ [AJAX LOGS ERROR] User does not have manage_options capability");
            wp_die(__('You do not have sufficient permissions to access this page.'));
        }
        error_log("✅ [AJAX LOGS STEP 1] User has manage_options capability");

        // Verify nonce
        if (!wp_verify_nonce($_POST['nonce'], 'eve_sync_nonce')) {
            error_log("❌ [AJAX LOGS ERROR] Nonce verification failed");
            error_log("🔄 [AJAX LOGS DEBUG] Received nonce: " . ($_POST['nonce'] ?? 'none'));
            error_log("🔄 [AJAX LOGS DEBUG] Expected nonce action: eve_sync_nonce");
            wp_send_json_error(array('message' => 'Security check failed'), 403);
            return;
        }
        error_log("✅ [AJAX LOGS STEP 2] Nonce verification passed");

        // Get parameters
        $lines = isset($_POST['lines']) ? intval($_POST['lines']) : 100;
        $search = isset($_POST['search']) ? sanitize_text_field($_POST['search']) : '';
        $levels_str = isset($_POST['levels']) ? sanitize_text_field($_POST['levels']) : '';
        $levels = !empty($levels_str) ? explode(',', $levels_str) : array('INFO', 'WARNING', 'ERROR', 'DEBUG');

        error_log("🔄 [AJAX LOGS STEP 3] Parameters - lines: {$lines}, search: {$search}, levels: " . print_r($levels, true));

        // Get the log file path
        $log_file = plugin_dir_path(__FILE__) . 'scripts/eve_observer.log';
        error_log("🔄 [AJAX LOGS STEP 4] Log file path: {$log_file}");

        if (!file_exists($log_file)) {
            error_log("❌ [AJAX LOGS ERROR] Log file does not exist: {$log_file}");
            wp_send_json_error(array('message' => 'Log file not found'), 404);
            return;
        }

        // Read the log file
        $log_content = file_get_contents($log_file);
        if ($log_content === false) {
            error_log("❌ [AJAX LOGS ERROR] Failed to read log file");
            wp_send_json_error(array('message' => 'Failed to read log file'), 500);
            return;
        }

        // Split into lines and reverse (newest first)
        $log_lines = array_reverse(explode("\n", trim($log_content)));
        error_log("🔄 [AJAX LOGS STEP 5] Total log lines: " . count($log_lines));

        // Filter and limit lines
        $filtered_logs = array();
        $line_count = 0;

        foreach ($log_lines as $line) {
            if ($line_count >= $lines) {
                break;
            }

            // Apply search filter
            if (!empty($search) && stripos($line, $search) === false) {
                continue;
            }

            // Apply log level filters
            $include_line = false;
            if (!empty($levels)) {
                foreach ($levels as $level) {
                    if (stripos($line, " - {$level} - ") !== false) {
                        $include_line = true;
                        break;
                    }
                }
            } else {
                // If no levels selected, include all lines
                $include_line = true;
            }

            if ($include_line) {
                // Parse log line into structured format
                $parsed_log = $this->parse_log_line($line);
                if ($parsed_log) {
                    $filtered_logs[] = $parsed_log;
                    $line_count++;
                }
            }
        }

        error_log("✅ [AJAX LOGS STEP 6] Filtered to {$line_count} lines");

        // Format the response
        $response = array(
            'success' => true,
            'logs' => $filtered_logs,
            'total_lines' => count($log_lines),
            'filtered_lines' => $line_count,
            'timestamp' => current_time('mysql')
        );

        error_log("✅ [AJAX LOGS SUCCESS] Returning {$line_count} log lines");
        wp_send_json_success($response);
    }

    private function parse_log_line($line) {
        // Expected format: "2024-01-15 10:30:45 - INFO - Message here"
        $pattern = '/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - ([A-Z]+) - (.+)$/';
        
        if (preg_match($pattern, $line, $matches)) {
            return array(
                'timestamp' => $matches[1],
                'level' => $matches[2],
                'message' => trim($matches[3])
            );
        }
        
        // Fallback: if line doesn't match expected format, treat whole line as message
        return array(
            'timestamp' => current_time('Y-m-d H:i:s'),
            'level' => 'UNKNOWN',
            'message' => $line
        );
    }

    public function handle_ajax_clear_logs_request() {
        // Log the start of AJAX request processing
        error_log("🔄 [AJAX CLEAR LOGS START] ========================================");
        error_log("🔄 [AJAX CLEAR LOGS START] handle_ajax_clear_logs_request called");
        error_log("🔄 [AJAX CLEAR LOGS START] Timestamp: " . current_time('mysql'));
        error_log("🔄 [AJAX CLEAR LOGS START] REQUEST_METHOD: " . ($_SERVER['REQUEST_METHOD'] ?? 'unknown'));
        error_log("🔄 [AJAX CLEAR LOGS START] POST data: " . print_r($_POST, true));
        error_log("🔄 [AJAX CLEAR LOGS START] GET data: " . print_r($_GET, true));
        error_log("🔄 [AJAX CLEAR LOGS START] Current user ID: " . get_current_user_id());
        error_log("🔄 [AJAX CLEAR LOGS START] Current user capabilities: " . print_r(wp_get_current_user()->allcaps, true));
        error_log("🔄 [AJAX CLEAR LOGS START] ========================================");

        // Check permissions
        if (!current_user_can('manage_options')) {
            error_log("❌ [AJAX CLEAR LOGS ERROR] User does not have manage_options capability");
            wp_die(__('You do not have sufficient permissions to access this page.'));
        }
        error_log("✅ [AJAX CLEAR LOGS STEP 1] User has manage_options capability");

        // Verify nonce
        if (!wp_verify_nonce($_POST['nonce'], 'eve_sync_nonce')) {
            error_log("❌ [AJAX CLEAR LOGS ERROR] Nonce verification failed");
            error_log("🔄 [AJAX CLEAR LOGS DEBUG] Received nonce: " . ($_POST['nonce'] ?? 'none'));
            error_log("🔄 [AJAX CLEAR LOGS DEBUG] Expected nonce action: eve_sync_nonce");
            wp_send_json_error(array('message' => 'Security check failed'), 403);
            return;
        }
        error_log("✅ [AJAX CLEAR LOGS STEP 2] Nonce verification passed");

        // Get the log file path
        $log_file = plugin_dir_path(__FILE__) . 'scripts/eve_observer.log';
        error_log("🔄 [AJAX CLEAR LOGS STEP 3] Log file path: {$log_file}");

        if (!file_exists($log_file)) {
            error_log("❌ [AJAX CLEAR LOGS ERROR] Log file does not exist: {$log_file}");
            wp_send_json_error(array('message' => 'Log file not found'), 404);
            return;
        }

        // Clear the log file by writing an empty string
        $result = file_put_contents($log_file, '');
        if ($result === false) {
            error_log("❌ [AJAX CLEAR LOGS ERROR] Failed to clear log file");
            wp_send_json_error(array('message' => 'Failed to clear log file'), 500);
            return;
        }

        error_log("✅ [AJAX CLEAR LOGS SUCCESS] Log file cleared successfully");

        // Log the clear action
        error_log("🔄 [ADMIN ACTION] Logs cleared by user ID: " . get_current_user_id());

        wp_send_json_success(array(
            'message' => 'Logs cleared successfully',
            'timestamp' => current_time('mysql')
        ));
    }

    public function handle_sync_request($request) {
        $section = $request->get_param('section');

        // Log the sync request
        error_log("🔄 [PHP STEP 1] EVE Observer: Sync request started for section: {$section}");
        error_log("🔄 [PHP STEP 2] Request parameters: " . print_r($request->get_params(), true));

        // Check if required functions are available
        error_log("🔄 [PHP STEP 3] Checking if shell_exec function is available...");
        if (!function_exists('shell_exec')) {
            error_log("❌ [PHP ERROR] shell_exec function is disabled");
            error_log("🔄 [PHP STEP 4] Returning error response for disabled function");
            return new WP_Error('function_disabled', 'shell_exec function is disabled by server configuration', array('status' => 500));
        }
        error_log("✅ [PHP STEP 5] shell_exec function is available");

        // Get the path to the scripts directory
        error_log("🔄 [PHP STEP 6] Getting plugin and scripts directory paths...");
        $plugin_dir = plugin_dir_path(__FILE__);
        $scripts_dir = $plugin_dir . 'scripts/';
        error_log("🔄 [PHP STEP 7] Plugin dir: {$plugin_dir}");
        error_log("🔄 [PHP STEP 8] Scripts dir: {$scripts_dir}");

        if (!is_dir($scripts_dir)) {
            error_log("❌ [PHP ERROR] Scripts directory not found: {$scripts_dir}");
            return new WP_Error('scripts_dir_not_found', 'Scripts directory not found: ' . $scripts_dir, array('status' => 500));
        }
        error_log("✅ [PHP STEP 9] Scripts directory exists");

        // Map sections to Python scripts
        error_log("🔄 [PHP STEP 10] Mapping section to Python script...");
        $script_map = array(
            'characters' => 'main.py --characters',
            'blueprints' => 'main.py --blueprints',
            'planets' => 'main.py --planets',
            'corporations' => 'main.py --corporations',
            'contracts' => 'main.py --contracts',
            'all' => 'main.py --all'
        );

        if (!isset($script_map[$section])) {
            error_log("❌ [PHP ERROR] Invalid section specified: {$section}");
            return new WP_Error('invalid_section', 'Invalid section specified', array('status' => 400));
        }
        error_log("✅ [PHP STEP 11] Section mapped to script: {$script_map[$section]}");

        // Parse script and arguments from script_map entry
        $script_parts = explode(' ', $script_map[$section], 2);
        $script_name = $script_parts[0]; // e.g., 'main.py'
        $script_args = isset($script_parts[1]) ? $script_parts[1] : ''; // e.g., '--all'
        error_log("🔄 [PHP STEP 12] Preparing shell command...");
        
        // Try multiple methods to find Python executable
        $python_cmd = '';
        $python_paths = array(
            '/usr/bin/python3',
            '/usr/local/bin/python3', 
            '/usr/bin/python',
            '/usr/local/bin/python',
            'python3',
            'python'
        );
        
        error_log("🔄 [PHP STEP 12.1] Checking for Python in common locations...");
        foreach ($python_paths as $path) {
            // Test if the Python executable exists and is executable
            $test_cmd = 'command -v ' . escapeshellarg($path) . ' 2>/dev/null && ' . escapeshellarg($path) . ' --version 2>/dev/null';
            $test_output = shell_exec($test_cmd);
            if (!empty($test_output) && strpos($test_output, 'Python') !== false) {
                $python_cmd = $path;
                error_log("✅ [PHP STEP 12.2] Found working Python at: {$path}");
                break;
            }
        }
        
        if (empty($python_cmd)) {
            error_log("❌ [PHP ERROR] No working Python executable found");
            error_log("🔄 [PHP STEP 12.3] Available commands check:");
            
            // Check what commands are available
            $which_output = shell_exec('which python3 python 2>/dev/null');
            error_log("🔄 [PHP STEP 12.4] which output: " . ($which_output ?: 'none'));
            
            $ls_output = shell_exec('ls -la /usr/bin/python* /usr/local/bin/python* 2>/dev/null | head -10');
            error_log("🔄 [PHP STEP 12.5] Python files in common dirs: " . ($ls_output ?: 'none'));
            
            return new WP_Error('python_not_found', 'Python executable not found. Your hosting provider (Hostinger) may not support Python, or it may be installed in a non-standard location. Please contact Hostinger support to enable Python or check if they offer Python hosting plans.', array('status' => 500));
        }
        
        error_log("✅ [PHP STEP 12.6] Using Python command: {$python_cmd}");
        
        // Build command with script name and arguments as separate arguments
        $command_parts = array(
            'cd', escapeshellarg($scripts_dir), '&&',
            escapeshellarg($python_cmd),
            escapeshellarg($script_name)
        );
        
        if (!empty($script_args)) {
            // Split arguments and add them individually
            $args_array = explode(' ', $script_args);
            foreach ($args_array as $arg) {
                $command_parts[] = escapeshellarg($arg);
            }
        }
        
        $command = implode(' ', $command_parts) . ' 2>&1';
        error_log("🔄 [PHP STEP 13] Full command: {$command}");

        // Set execution time limit for long-running syncs
        error_log("🔄 [PHP STEP 14] Setting PHP execution time limit to 300 seconds...");
        set_time_limit(300); // 5 minutes
        error_log("✅ [PHP STEP 15] Time limit set");

        // Execute the command and capture output
        error_log("🔄 [PHP STEP 16] Starting command execution...");
        $start_time = microtime(true);
        $output = shell_exec($command);
        $execution_time = microtime(true) - $start_time;
        error_log("✅ [PHP STEP 17] Command execution completed in " . round($execution_time, 2) . " seconds");

        // Check if command was successful (exit code 0)
        error_log("🔄 [PHP STEP 18] Checking command exit code...");
        $exit_code = 0;
        if (function_exists('exec')) {
            $last_line = exec($command, $output_lines, $exit_code);
            error_log("🔄 [PHP STEP 19] Exit code from exec(): {$exit_code}");
        }

        if ($exit_code !== 0) {
            error_log("❌ [PHP ERROR] Sync failed for section {$section}. Exit code: {$exit_code}. Output: " . substr($output, 0, 1000));
            error_log("🔄 [PHP STEP 20] Returning error response for failed command");
            return new WP_Error('sync_failed', 'Sync failed with exit code: ' . $exit_code, array('status' => 500));
        }

        // Log successful completion
        error_log("✅ [PHP STEP 21] Sync completed successfully for section {$section} in " . round($execution_time, 2) . " seconds");
        error_log("🔄 [PHP STEP 22] Preparing success response...");

        $response = array(
            'success' => true,
            'section' => $section,
            'message' => 'Sync completed successfully',
            'execution_time' => round($execution_time, 2),
            'timestamp' => current_time('mysql'),
            'output' => $output
        );
        error_log("✅ [PHP STEP 23] Success response prepared: " . print_r($response, true));

        return $response;
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
        // Dashboard-specific scripts and styles
        if ($hook === 'toplevel_page_eve-observer') {
            wp_enqueue_style('eve-observer-dashboard', plugin_dir_url(__FILE__) . 'css/dashboard.css', array(), '1.1.1');
            wp_enqueue_script('chart-js', 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js', array(), '4.4.1', true);
            wp_enqueue_script('eve-observer-dashboard', plugin_dir_url(__FILE__) . 'js/dashboard.js', array('chart-js'), '1.2.1', false);

            // Localize script with nonce and AJAX URL
            $localized_data = array(
                'nonce' => wp_create_nonce('eve_sync_nonce'),
                'ajaxUrl' => admin_url('admin-ajax.php')
            );
            wp_localize_script('eve-observer-dashboard', 'eveObserverApi', $localized_data);

            error_log("🔄 [ENQUEUE] Localized eveObserverApi with data: " . print_r($localized_data, true));

            // Add clipboard functionality for dashboard
            wp_add_inline_script('eve-observer-dashboard', '
                console.log("Clipboard functions loading");
                function copyToClipboard(text) {
                    console.log("copyToClipboard called with text length:", text.length);
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
                console.log("Clipboard functions loaded");
            ');
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
                <div class="eve-dashboard-actions">
                    <button id="eve-sync-all" class="button button-primary">
                        <span class="dashicons dashicons-update"></span>
                        <?php _e('Sync All Data', 'eve-observer'); ?>
                    </button>
                    <button id="eve-test-logging" class="button button-secondary" style="margin-left: 10px;">
                        <span class="dashicons dashicons-search"></span>
                        <?php _e('Test Logging', 'eve-observer'); ?>
                    </button>
                    <button id="eve-test-api" class="button button-secondary" style="margin-left: 10px;">
                        <span class="dashicons dashicons-rest-api"></span>
                        <?php _e('Test API', 'eve-observer'); ?>
                    </button>
                </div>
            </div>

            <!-- Sync Progress Area -->
            <div id="sync-progress-container" style="display: none; margin-top: 20px;">
                <h3><?php _e('Sync Progress', 'eve-observer'); ?></h3>

                <!-- Individual Sync Progress Areas -->
                <div id="sync-progress-characters" class="sync-progress-item" style="display: none; margin-bottom: 15px; padding: 15px; background: #f9f9f9; border: 1px solid #ddd; border-radius: 4px;">
                    <h4>Characters Sync</h4>
                    <div class="eve-progress-bar">
                        <div class="eve-progress-fill" id="sync-progress-characters-fill" style="width: 0%;"></div>
                    </div>
                    <div class="eve-progress-text" id="sync-progress-characters-text">Initializing...</div>
                    <pre id="sync-progress-characters-content" style="font-family: monospace; font-size: 12px; white-space: pre-wrap; margin: 10px 0 0 0; max-height: 200px; overflow-y: auto;"></pre>
                </div>

                <div id="sync-progress-blueprints" class="sync-progress-item" style="display: none; margin-bottom: 15px; padding: 15px; background: #f9f9f9; border: 1px solid #ddd; border-radius: 4px;">
                    <h4>Blueprints Sync</h4>
                    <div class="eve-progress-bar">
                        <div class="eve-progress-fill" id="sync-progress-blueprints-fill" style="width: 0%;"></div>
                    </div>
                    <div class="eve-progress-text" id="sync-progress-blueprints-text">Initializing...</div>
                    <pre id="sync-progress-blueprints-content" style="font-family: monospace; font-size: 12px; white-space: pre-wrap; margin: 10px 0 0 0; max-height: 200px; overflow-y: auto;"></pre>
                </div>

                <div id="sync-progress-planets" class="sync-progress-item" style="display: none; margin-bottom: 15px; padding: 15px; background: #f9f9f9; border: 1px solid #ddd; border-radius: 4px;">
                    <h4>Planets Sync</h4>
                    <div class="eve-progress-bar">
                        <div class="eve-progress-fill" id="sync-progress-planets-fill" style="width: 0%;"></div>
                    </div>
                    <div class="eve-progress-text" id="sync-progress-planets-text">Initializing...</div>
                    <pre id="sync-progress-planets-content" style="font-family: monospace; font-size: 12px; white-space: pre-wrap; margin: 10px 0 0 0; max-height: 200px; overflow-y: auto;"></pre>
                </div>

                <div id="sync-progress-corporations" class="sync-progress-item" style="display: none; margin-bottom: 15px; padding: 15px; background: #f9f9f9; border: 1px solid #ddd; border-radius: 4px;">
                    <h4>Corporations Sync</h4>
                    <div class="eve-progress-bar">
                        <div class="eve-progress-fill" id="sync-progress-corporations-fill" style="width: 0%;"></div>
                    </div>
                    <div class="eve-progress-text" id="sync-progress-corporations-text">Initializing...</div>
                    <pre id="sync-progress-corporations-content" style="font-family: monospace; font-size: 12px; white-space: pre-wrap; margin: 10px 0 0 0; max-height: 200px; overflow-y: auto;"></pre>
                </div>

                <div id="sync-progress-contracts" class="sync-progress-item" style="display: none; margin-bottom: 15px; padding: 15px; background: #f9f9f9; border: 1px solid #ddd; border-radius: 4px;">
                    <h4>Contracts Sync</h4>
                    <div class="eve-progress-bar">
                        <div class="eve-progress-fill" id="sync-progress-contracts-fill" style="width: 0%;"></div>
                    </div>
                    <div class="eve-progress-text" id="sync-progress-contracts-text">Initializing...</div>
                    <pre id="sync-progress-contracts-content" style="font-family: monospace; font-size: 12px; white-space: pre-wrap; margin: 10px 0 0 0; max-height: 200px; overflow-y: auto;"></pre>
                </div>

                <div id="sync-progress-all" class="sync-progress-item" style="display: none; margin-bottom: 15px; padding: 15px; background: #f9f9f9; border: 1px solid #ddd; border-radius: 4px;">
                    <h4>All Data Sync</h4>
                    <div class="eve-progress-bar">
                        <div class="eve-progress-fill" id="sync-progress-all-fill" style="width: 0%;"></div>
                    </div>
                    <div class="eve-progress-text" id="sync-progress-all-text">Initializing...</div>
                    <pre id="sync-progress-all-content" style="font-family: monospace; font-size: 12px; white-space: pre-wrap; margin: 10px 0 0 0; max-height: 200px; overflow-y: auto;"></pre>
                </div>
            </div>

            <!-- Sync Status Display -->
            <div id="sync-status-display" style="display: none; margin-top: 20px; padding: 15px; background: #e8f5e8; border: 1px solid #28a745; border-radius: 4px;">
                <h3><?php _e('Sync Status', 'eve-observer'); ?></h3>
                <div id="sync-status-progress" style="margin-bottom: 10px;">
                    <div class="eve-progress-bar">
                        <div class="eve-progress-fill" style="width: 0%; background-color: #28a745;"></div>
                    </div>
                    <div class="eve-progress-text" id="sync-status-text">Checking status...</div>
                </div>
                <button id="stop-sync-button" class="button button-secondary" style="display: none;">
                    <span class="dashicons dashicons-no"></span>
                    <?php _e('Stop Sync', 'eve-observer'); ?>
                </button>
            </div>

            <!-- Overview Cards -->
            <div class="eve-overview-grid">
                <div class="eve-card eve-card-clickable" data-section="characters">
                    <div class="eve-card-header">
                        <div class="eve-card-title-group">
                            <div class="eve-card-icon" style="background: rgba(0, 122, 255, 0.1); color: var(--primary-color);">👤</div>
                            <h3 class="eve-card-title"><?php _e('Characters', 'eve-observer'); ?></h3>
                        </div>
                        <button class="eve-sync-btn" data-section="characters" title="Sync Characters">
                            <span class="dashicons dashicons-update"></span>
                        </button>
                    </div>
                    <p class="eve-card-value"><?php echo esc_html($character_count); ?></p>
                </div>

                <div class="eve-card eve-card-clickable" data-section="blueprints">
                    <div class="eve-card-header">
                        <div class="eve-card-title-group">
                            <div class="eve-card-icon" style="background: rgba(255, 149, 0, 0.1); color: var(--warning-color);">📋</div>
                            <h3 class="eve-card-title"><?php _e('Blueprints', 'eve-observer'); ?></h3>
                        </div>
                        <button class="eve-sync-btn" data-section="blueprints" title="Sync Blueprints">
                            <span class="dashicons dashicons-update"></span>
                        </button>
                    </div>
                    <p class="eve-card-value"><?php echo esc_html($blueprint_count); ?></p>
                </div>

                <div class="eve-card eve-card-clickable" data-section="planets">
                    <div class="eve-card-header">
                        <div class="eve-card-title-group">
                            <div class="eve-card-icon" style="background: rgba(52, 199, 89, 0.1); color: var(--success-color);">🌍</div>
                            <h3 class="eve-card-title"><?php _e('Planets', 'eve-observer'); ?></h3>
                        </div>
                        <button class="eve-sync-btn" data-section="planets" title="Sync Planets">
                            <span class="dashicons dashicons-update"></span>
                        </button>
                    </div>
                    <p class="eve-card-value"><?php echo esc_html($planet_count); ?></p>
                </div>

                <div class="eve-card eve-card-clickable" data-section="corporations">
                    <div class="eve-card-header">
                        <div class="eve-card-title-group">
                            <div class="eve-card-icon" style="background: rgba(255, 59, 48, 0.1); color: var(--danger-color);">🏢</div>
                            <h3 class="eve-card-title"><?php _e('Corporations', 'eve-observer'); ?></h3>
                        </div>
                        <button class="eve-sync-btn" data-section="corporations" title="Sync Corporations">
                            <span class="dashicons dashicons-update"></span>
                        </button>
                    </div>
                    <p class="eve-card-value"><?php echo esc_html($corporation_count); ?></p>
                </div>

                <div class="eve-card eve-card-clickable" data-section="contracts">
                    <div class="eve-card-header">
                        <div class="eve-card-title-group">
                            <div class="eve-card-icon" style="background: rgba(142, 142, 147, 0.1); color: #8e8e93;">📄</div>
                            <h3 class="eve-card-title"><?php _e('Contracts', 'eve-observer'); ?></h3>
                        </div>
                        <button class="eve-sync-btn" data-section="contracts" title="Sync Contracts">
                            <span class="dashicons dashicons-update"></span>
                        </button>
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
                                <th><?php _e('Competing Price', 'eve-observer'); ?></th>
                                <th><?php _e('Outbid', 'eve-observer'); ?></th>
                            </tr>
                        </thead>
                        <tbody id="contracts-tbody">
                            <!-- Contracts will be loaded here -->
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Log Viewer Section -->
            <div class="eve-data-section" id="logs-section">
                <h2><?php _e('EVE Observer Logs', 'eve-observer'); ?></h2>
                <div class="eve-section-actions">
                    <button id="refresh-logs" class="button button-secondary">
                        <span class="dashicons dashicons-update"></span>
                        <?php _e('Refresh Logs', 'eve-observer'); ?>
                    </button>
                    <button id="clear-logs" class="button button-secondary" style="margin-left: 10px;">
                        <span class="dashicons dashicons-trash"></span>
                        <?php _e('Clear Logs', 'eve-observer'); ?>
                    </button>
                    <div style="float: right;">
                        <label for="log-lines"><?php _e('Lines to show:', 'eve-observer'); ?></label>
                        <select id="log-lines" style="margin-left: 5px;">
                            <option value="50">50</option>
                            <option value="100">100</option>
                            <option value="200">200</option>
                            <option value="500">500</option>
                            <option value="1000">1000</option>
                        </select>
                    </div>
                </div>
                <div class="eve-loading" id="logs-loading">
                    <div class="eve-loading-spinner"></div>
                    <span>Loading logs...</span>
                </div>
                <div id="logs-content" style="display: none;">
                    <div class="eve-search-container">
                        <input type="text" class="eve-search-input" id="logs-search" placeholder="Search logs...">
                        <div style="margin-top: 10px;">
                            <label><input type="checkbox" id="log-filter-info" checked> INFO</label>
                            <label style="margin-left: 15px;"><input type="checkbox" id="log-filter-warning" checked> WARNING</label>
                            <label style="margin-left: 15px;"><input type="checkbox" id="log-filter-error" checked> ERROR</label>
                            <label style="margin-left: 15px;"><input type="checkbox" id="log-filter-debug" checked> DEBUG</label>
                        </div>
                    </div>
                    <div id="logs-container" style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 15px; max-height: 600px; overflow-y: auto; font-family: 'Courier New', monospace; font-size: 12px; line-height: 1.4;">
                        <pre id="logs-display" style="margin: 0; white-space: pre-wrap;"></pre>
                    </div>
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
                    'key' => 'field_contract_availability',
                    'label' => 'Availability',
                    'name' => '_eve_contract_availability',
                    'type' => 'select',
                    'choices' => array(
                        'public' => 'Public',
                        'personal' => 'Personal',
                        'corporation' => 'Corporation',
                        'alliance' => 'Alliance',
                    ),
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_for_corporation',
                    'label' => 'For Corporation',
                    'name' => '_eve_contract_for_corporation',
                    'type' => 'true_false',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_issuer_id',
                    'label' => 'Issuer ID',
                    'name' => '_eve_contract_issuer_id',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_issuer_name',
                    'label' => 'Issuer Name',
                    'name' => '_eve_contract_issuer_name',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_issuer_corporation_id',
                    'label' => 'Issuer Corporation ID',
                    'name' => '_eve_contract_issuer_corporation_id',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_issuer_corporation_name',
                    'label' => 'Issuer Corporation Name',
                    'name' => '_eve_contract_issuer_corporation_name',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_assignee_id',
                    'label' => 'Assignee ID',
                    'name' => '_eve_contract_assignee_id',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_assignee_name',
                    'label' => 'Assignee Name',
                    'name' => '_eve_contract_assignee_name',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_location_id',
                    'label' => 'Location ID',
                    'name' => '_eve_contract_location_id',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_location_name',
                    'label' => 'Location Name',
                    'name' => '_eve_contract_location_name',
                    'type' => 'text',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_region_id',
                    'label' => 'Region ID',
                    'name' => '_eve_contract_region_id',
                    'type' => 'number',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_date_issued',
                    'label' => 'Date Issued',
                    'name' => '_eve_contract_date_issued',
                    'type' => 'date_time_picker',
                    'display_format' => 'Y-m-d H:i:s',
                    'return_format' => 'Y-m-d H:i:s',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_date_expired',
                    'label' => 'Date Expired',
                    'name' => '_eve_contract_date_expired',
                    'type' => 'date_time_picker',
                    'display_format' => 'Y-m-d H:i:s',
                    'return_format' => 'Y-m-d H:i:s',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_date_accepted',
                    'label' => 'Date Accepted',
                    'name' => '_eve_contract_date_accepted',
                    'type' => 'date_time_picker',
                    'display_format' => 'Y-m-d H:i:s',
                    'return_format' => 'Y-m-d H:i:s',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_date_completed',
                    'label' => 'Date Completed',
                    'name' => '_eve_contract_date_completed',
                    'type' => 'date_time_picker',
                    'display_format' => 'Y-m-d H:i:s',
                    'return_format' => 'Y-m-d H:i:s',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_price',
                    'label' => 'Price (ISK)',
                    'name' => '_eve_contract_price',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_reward',
                    'label' => 'Reward (ISK)',
                    'name' => '_eve_contract_reward',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_collateral',
                    'label' => 'Collateral (ISK)',
                    'name' => '_eve_contract_collateral',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_buyout',
                    'label' => 'Buyout (ISK)',
                    'name' => '_eve_contract_buyout',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_market_price',
                    'label' => 'Market Price (ISK)',
                    'name' => '_eve_contract_market_price',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_volume',
                    'label' => 'Volume (m³)',
                    'name' => '_eve_contract_volume',
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
                    'key' => 'field_contract_outbid',
                    'label' => 'Outbid',
                    'name' => '_eve_contract_outbid',
                    'type' => 'true_false',
                    'message' => 'This contract has been outbid',
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_competing_price',
                    'label' => 'Competing Price (ISK)',
                    'name' => '_eve_contract_competing_price',
                    'type' => 'number',
                    'step' => 0.01,
                    'show_in_rest' => true,
                ),
                array(
                    'key' => 'field_contract_items',
                    'label' => 'Contract Items (JSON)',
                    'name' => '_eve_contract_items',
                    'type' => 'textarea',
                    'rows' => 10,
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

        // Register meta fields for contracts
        register_meta('post', '_eve_contract_region_id', array(
            'type' => 'string',
            'description' => 'Region ID for the contract',
            'single' => true,
            'show_in_rest' => true,
            'auth_callback' => '__return_true'
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
            $is_outbid = get_post_meta($post_id, '_eve_contract_outbid', true) === '1';
            $contract_id = get_post_meta($post_id, '_eve_contract_id', true);
            $contract_title = get_post_meta($post_id, '_eve_contract_title', true);
            $start_location_id = get_post_meta($post_id, '_eve_contract_location_id', true);
            $competing_price = get_post_meta($post_id, '_eve_contract_competing_price', true);

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
                $region_id = get_post_meta($post_id, '_eve_contract_region_id', true);
                if (empty($region_id)) {
                    // Fallback to location_id if region_id not available
                    $region_id = $start_location_id;
                    if (empty($region_id)) {
                        $region_id = get_post_meta($post_id, '_eve_contract_end_location_id', true);
                    }
                }
                if (!empty($region_id)) {
                    $eve_link = '<font size="14" color="#bfffffff"><br></font><font size="14" color="#ffd98d00"><a href="contract:' . $region_id . '//' . $contract_id . '">[Contract ' . $contract_id . ']</a></font>';
                } else {
                    // Fallback: create link without location (might still work in some cases)
                    $eve_link = '<font size="14" color="#bfffffff"><br></font><font size="14" color="#ffd98d00"><a href="contract://' . $contract_id . '">[Contract ' . $contract_id . ']</a></font>';
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

            if ($is_outbid && !empty($competing_price) && is_numeric($competing_price)) {
                $formatted_price = number_format((float)$competing_price, 2);
                echo "<span style='color: #666; font-size: 12px; cursor: pointer;' onclick='copyToClipboard(" . json_encode($formatted_price) . ")' title='Click to copy competing price'>Competing: " . esc_html($formatted_price) . " ISK</span>";
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
