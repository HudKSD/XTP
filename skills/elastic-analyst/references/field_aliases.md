# Field Alias Hints

These are common meaning-level aliases for this incident-analysis / security-article index.

- date / time / timestamp -> `Timestamp`, `@timestamp`, `ingested_at`
  - Prefer `Timestamp` as the default for this index unless schema inspection shows otherwise.
- title / headline -> `Title`
- source / article source / source url -> `Source`, `article_url`
- cve / vulnerability -> verify with schema tools first; common candidates may include `Extracted_Entities.CVEs`, `Capability.Exploits`, or other index-specific CVE fields
- summary / article summary / overview -> `doc_summary`
- severity / risk level -> `Severity`, `Victim.Impact_Severity`
- threat actor / actor / attacker -> `Threat_Actors`, `Adversary.Associated_Groups`, `Adversary.Aliases`
- adversary / campaign / group -> `Adversary.Known_Campaigns`, `Adversary.Aliases`, `Adversary.Associated_Groups`, `Adversary.Motivation`, `Adversary.Strategic_Objectives`, `Adversary.Sophistication`
- victim / target -> `Victim.Description`, `Victim.Targeted_Assets`, `Victim.Access_Vectors`, `Victim.Data_Types_At_Risk`
- industry / sector -> `Victim.Industry`, `stats.topics.people.sector`
- geography / country / location -> `Victim.Geography`, `stats.topics.people.country`
- company / organization -> `stats.topics.people.company`, `stats.topics.people.name`
- role / title -> `stats.topics.people.role_or_title`
- sentiment -> `stats.topics.sentiment`, `stats.topics.people.sentiment`
- topic / classification -> `stats.topics.topic`, `stats.topics.Text_Classification`, `stats.topics.summary`
- question / answer / qa -> `stats.topics.Information_Retrieval_and_Question_Answering.questions_and_answers.question`, `stats.topics.Information_Retrieval_and_Question_Answering.questions_and_answers.answer`
- kill chain / attack stage -> `Analyses.Stage`, `kill_chain_summary`
- tactics -> `Analyses.Tactics.tactic_name`, `Analyses.Tactics.tactic_id`, `Analyses.Tactics.tactic_description`
- techniques / mitre techniques -> `Analyses.Techniques.technique_name`, `Analyses.Techniques.technique_id`, `Analyses.Techniques.technique_description`
- detection / detections -> `Analyses.Detection`, `Detection_Rules_And_Indicators`
- remediation / recommendations / actions -> `Analyses.Remediation`, `Post_Incident_Recommendations`, `Recommended_Tools_And_Techniques_For_Analysis`
- behavioral indicators / attacker behavior -> `Behavioral_Indicators_of_Attackers`
- exfiltration / data theft indicators -> `Data_Exfiltration_Indicators`
- infrastructure / network infrastructure -> `Infrastructure.Description`, `Infrastructure.Domains`, `Infrastructure.IPs`, `Infrastructure.C2_Servers`, `Infrastructure.Hosting_Providers`, `Infrastructure.SSL_Certificates`, `Infrastructure.Botnets`, `Infrastructure.Communication_Protocols`
- capability / tools / malware / exploits -> `Capability.Description`, `Capability.Tools`, `Capability.Malware`, `Capability.Exploits`, `Capability.Zero_Days`, `Capability.Persistence_Mechanisms`, `Capability.Lateral_Movement_Tools`, `Capability.Defensive_Evasion_Tactics`
- pyramid of pain -> `Pyramid_Of_Pain.TTPs`, `Pyramid_Of_Pain.Tools`, `Pyramid_Of_Pain.Domain_Names`, `Pyramid_Of_Pain.IP_Addresses`, `Pyramid_Of_Pain.Hash_Values`, `Pyramid_Of_Pain.Network_Host_Artifacts`, `Pyramid_Of_Pain_Scoring.percentage`, `Pyramid_Of_Pain_Scoring.raw_score`, `pyramid_of_pain_summary`
- diamond model -> `diamond_model_summary`
- sequence / ordering -> `sequence`

The actual mapping wins over this hint file. Always verify with schema tools.
