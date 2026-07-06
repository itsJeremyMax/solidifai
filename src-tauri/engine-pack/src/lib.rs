//! engine-pack: the manifest + pack format for solidifai engine updates.
//! One implementation, shared by the runtime (links the lib) and CI (calls the bin).

pub mod archive;
pub mod hash;
pub mod manifest;
pub mod verify;

#[cfg(test)]
mod smoke {
    #[test]
    fn crate_builds() {
        assert_eq!(2 + 2, 4);
    }
}
