//! Which content-addressed engine this build requires. CI stamps `engine-pin.json`;
//! a dev build ships the `"dev"` sentinel and resolves the engine the old way.

#[derive(serde::Deserialize, Clone, Debug, PartialEq, Eq)]
pub struct EnginePin {
    #[serde(rename = "engineRev")]
    pub engine_rev: String,
    #[serde(rename = "manifestHash")]
    pub manifest_hash: String,
}

impl EnginePin {
    pub fn embedded() -> Self {
        serde_json::from_str(include_str!("../engine-pin.json")).expect("engine-pin.json valid")
    }

    pub fn is_dev(&self) -> bool {
        self.manifest_hash == "dev"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_embedded_pin() {
        let p = EnginePin::embedded();
        assert!(!p.engine_rev.is_empty() && !p.manifest_hash.is_empty());
    }

    #[test]
    fn dev_sentinel_detected() {
        let p: EnginePin =
            serde_json::from_str(r#"{"engineRev":"dev","manifestHash":"dev"}"#).unwrap();
        assert!(p.is_dev());
    }

    #[test]
    fn real_pin_is_not_dev() {
        let p: EnginePin =
            serde_json::from_str(r#"{"engineRev":"e3f9","manifestHash":"9c2f"}"#).unwrap();
        assert!(!p.is_dev());
        assert_eq!(p.engine_rev, "e3f9");
    }
}
