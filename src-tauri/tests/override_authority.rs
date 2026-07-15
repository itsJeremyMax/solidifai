use std::time::Duration;

use solidifai_lib::override_authority::OverrideAuthority;

#[test]
fn consumes_only_one_matching_live_nonce() {
    let authority = OverrideAuthority::new(Duration::from_secs(60));
    let nonce = authority.issue("/workspace", 7, "stl");

    assert!(authority.consume(&nonce, "/workspace", 7, "stl").is_some());
    assert!(authority.consume(&nonce, "/workspace", 7, "stl").is_none());
}

#[test]
fn rejects_forged_expired_and_wrong_scope_nonces() {
    let authority = OverrideAuthority::new(Duration::from_millis(0));
    let expired = authority.issue("/workspace", 7, "stl");
    assert!(authority
        .consume(&expired, "/workspace", 7, "stl")
        .is_none());

    let authority = OverrideAuthority::new(Duration::from_secs(60));
    let nonce = authority.issue("/workspace", 7, "stl");
    assert!(authority
        .consume("forged", "/workspace", 7, "stl")
        .is_none());
    assert!(authority.consume(&nonce, "/workspace", 8, "stl").is_none());
    assert!(authority.consume(&nonce, "/workspace", 7, "step").is_none());
}
