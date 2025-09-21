<?php
/**
 * EVE Observer Blueprint Cleanup Script
 * Run this script to remove BPC posts from WordPress database
 */

// Load WordPress environment
require_once('wp-load.php');

if (!defined('ABSPATH')) {
    die('WordPress environment not loaded.');
}

// Check if user is logged in or has permissions
if (!current_user_can('delete_posts')) {
    die('Insufficient permissions to delete posts.');
}

echo "Starting BPC cleanup...\n";

// Get all blueprint posts
$args = array(
    'post_type' => 'eve_blueprint',
    'posts_per_page' => -1,
    'post_status' => 'any'
);

$blueprints = get_posts($args);
$total_posts = count($blueprints);
$deleted_count = 0;

echo "Found {$total_posts} blueprint posts\n";

foreach ($blueprints as $post) {
    $quantity = get_post_meta($post->ID, '_eve_bp_quantity', true);

    // If quantity is not -1, it's a BPC (Blueprint Copy)
    if ($quantity != -1) {
        $bp_id = get_post_meta($post->ID, '_eve_bp_item_id', true);
        echo "Deleting BPC: {$bp_id} (Post ID: {$post->ID})\n";

        // Delete the post permanently
        $result = wp_delete_post($post->ID, true);

        if ($result) {
            $deleted_count++;
            echo "Successfully deleted post {$post->ID}\n";
        } else {
            echo "Failed to delete post {$post->ID}\n";
        }
    }
}

echo "\nCleanup complete!\n";
echo "Total posts processed: {$total_posts}\n";
echo "BPCs deleted: {$deleted_count}\n";
echo "BPOs remaining: " . ($total_posts - $deleted_count) . "\n";
?>