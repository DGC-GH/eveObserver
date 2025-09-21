<?php
/**
 * BPC Cleanup Script for WordPress
 * This script removes all Blueprint Copies (BPCs) from the WordPress database
 * while preserving Blueprint Originals (BPOs).
 *
 * Run this script by uploading it to your WordPress root directory and accessing it via browser.
 * Make sure to delete this file after running it for security.
 */

// Load WordPress environment
require_once('wp-load.php');

// Check if user is logged in and is admin
if (!is_user_logged_in() || !current_user_can('administrator')) {
    wp_die('You must be logged in as an administrator to run this script.');
}

echo "<h1>EVE Observer - BPC Cleanup Script</h1>";
echo "<p>Starting cleanup process...</p>";

// Get all blueprint posts
$args = array(
    'post_type' => 'eve_blueprint',
    'posts_per_page' => -1,
    'post_status' => 'any'
);

$blueprints = get_posts($args);
$total_posts = count($blueprints);
$deleted_count = 0;
$kept_count = 0;

echo "<p>Found {$total_posts} blueprint posts to process.</p>";
echo "<ul>";

foreach ($blueprints as $blueprint) {
    $quantity = get_post_meta($blueprint->ID, '_eve_bp_quantity', true);

    // Check if this is a BPC (quantity != -1)
    if ($quantity != -1) {
        // This is a BPC - delete it
        $result = wp_delete_post($blueprint->ID, true); // true = force delete, bypass trash

        if ($result) {
            echo "<li style='color: green;'>✓ Deleted BPC: {$blueprint->post_title} (ID: {$blueprint->ID}, Quantity: {$quantity})</li>";
            $deleted_count++;
        } else {
            echo "<li style='color: red;'>✗ Failed to delete BPC: {$blueprint->post_title} (ID: {$blueprint->ID})</li>";
        }
    } else {
        // This is a BPO - keep it
        echo "<li style='color: blue;'>○ Kept BPO: {$blueprint->post_title} (ID: {$blueprint->ID}, Quantity: {$quantity})</li>";
        $kept_count++;
    }
}

echo "</ul>";
echo "<h2>Cleanup Complete</h2>";
echo "<p><strong>Summary:</strong></p>";
echo "<ul>";
echo "<li>Deleted BPCs: {$deleted_count}</li>";
echo "<li>Kept BPOs: {$kept_count}</li>";
echo "<li>Total processed: " . ($deleted_count + $kept_count) . "</li>";
echo "</ul>";

echo "<p style='color: red; font-weight: bold;'>⚠️ SECURITY NOTICE: Please delete this file immediately after verifying the results!</p>";
?></content>
<parameter name="filePath">/Users/dg/Documents/GitHub/eveObserver/scripts/cleanup_bpcs.php