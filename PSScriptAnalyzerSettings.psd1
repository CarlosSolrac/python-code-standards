# PSScriptAnalyzer settings for every tracked .ps1 file; CI runs the analyzer with this file.
# The scripts are standalone tools and hook commands, not a published module, so the rules
# below, which shape a module's public commands, do not apply to their private helpers.
@{
    Severity     = @('Error', 'Warning')
    ExcludeRules = @(
        # Helpers such as Stop-Sync and New-Payload are script-private; -WhatIf/-Confirm would never be passed.
        'PSUseShouldProcessForStateChangingFunctions',
        # Test helpers read as sentences (Test-Blocks: "the hook blocks"); a singular noun would change their meaning.
        'PSUseSingularNouns'
    )
}
