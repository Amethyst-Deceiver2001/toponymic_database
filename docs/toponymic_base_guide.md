# Comprehensive Guide to Building Mariupol Property Seizure Investigation System

**Building a toponymic database and document scraper system to document systematic property seizures in occupied Mariupol represents a critical investigative journalism project with significant technical, legal, and ethical complexities**. This comprehensive guide synthesizes best practices from leading war crimes documentation projects, technical implementation standards, and collaborative investigative journalism methodologies to provide actionable recommendations for creating a robust evidence collection system.

The investigation faces unique challenges: tracking systematic toponymic manipulation as a tool of occupation, processing Russian-language legal documents, and maintaining court-admissible evidence standards while protecting sources and investigators. Drawing from projects like Bellingcat's TimeMap database, Syrian Archive's digital evidence workflows, and the International Criminal Court's OTPLink platform, this guide provides a roadmap for building investigative infrastructure that can scale to handle large document volumes while meeting international legal standards.

## Database architecture for multi-lingual toponymic tracking

The foundation of effective property seizure documentation requires a sophisticated database architecture capable of handling **temporal toponymic changes across multiple languages and naming authorities**. The core challenge involves tracking Ukrainian pre-2022 place names alongside Russian post-invasion renames while maintaining historical accuracy and enabling precise address matching.

**Implement a translation subschema pattern** using three interconnected tables: `languages` for managing Ukrainian, Russian, and transliterated variants; `translatable_texts` for storing original place names with metadata; and `text_translations` for maintaining all naming variants with temporal validity periods. This architecture enables tracking of systematic naming changes while preserving historical accuracy.

The location entity structure should separate geographic points from their textual representations, using coordinates as the stable identifier while allowing multiple name variants. **Create composite indexes on normalized address fields** and implement fuzzy matching capabilities using Levenshtein distance algorithms to handle OCR errors and spelling variations in scraped documents.

For property seizure tracking, establish separate entities for seizure events, legal authorities, and property ownership changes. Each seizure event should link to specific addresses through the toponymic database while maintaining complete provenance records. This structure enables analysis of seizure patterns across different neighborhoods and identification of systematic targeting.

PostgreSQL with PostGIS extensions provides optimal support for spatial queries and full-text search across Cyrillic text. Implement comprehensive logging of all database changes to maintain legal chain-of-custody standards, with encrypted backup systems for sensitive evidence preservation.

## SpaCy implementation for Russian legal document processing

Russian-language named entity recognition requires **specialized pipeline configuration combining official spaCy models with custom legal terminology training**. The `ru_core_news_md` model provides foundational Russian language processing, but legal document analysis demands additional customization for property-specific terminology and address extraction patterns.

Implement custom SpaCy components for legal document preprocessing, including normalization of Cyrillic characters, removal of document headers and administrative text, and standardization of address formatting. Legal documents often contain OCR artifacts and non-standard formatting that require specialized handling before NLP processing.

**Configure address extraction patterns** targeting Russian legal terminology: "улица" (street), "проспект" (avenue), "дом" (house), "квартира" (apartment), and administrative variants used in official documents. Create entity rulers for systematic recognition of property types, legal authorities, and seizure-related terminology.

Training data should include annotated samples of actual seizure notices, focusing on address formats, property descriptions, and legal authority identifications. Implement active learning workflows where the model identifies uncertain extractions for human review, continuously improving accuracy through feedback loops.

For quality assurance, validate extracted entities against the toponymic database to identify potential errors or inconsistencies. Implement confidence scoring for all extractions, flagging low-confidence results for manual verification by investigators.

## Web scraping architecture for government sites

**Government sites implementing anti-scraping measures require sophisticated technical approaches balancing detection avoidance with legal compliance**. The target sites (mariupol-r897.gosweb.gosuslugi.ru and similar) likely implement rate limiting, IP blocking, and JavaScript-heavy interfaces requiring browser automation.

Use residential proxy pools with geographic distribution to avoid IP-based blocking while implementing respectful crawling practices. **Scrapy framework with custom middleware** provides robust foundation for handling retries, session management, and proxy rotation. Configure download delays between 2-5 seconds with randomization to mimic human browsing patterns.

For JavaScript-heavy sites, implement Playwright or Selenium integration to handle dynamic content loading. Many government portals load content asynchronously, requiring explicit waits for document lists and PDF links to appear. **Maintain persistent browser sessions** to handle authentication requirements while implementing proper cookie and session management.

PDF download workflows should verify document authenticity through hash checking and metadata extraction. Implement comprehensive error handling for network issues, server timeouts, and malformed documents. Queue-based processing using Celery allows for parallel document processing while maintaining request rate limits.

Legal considerations require **focusing on publicly accessible information without circumventing technical access controls**. Terms of service violations create civil liability risks, but scraping publicly available legal notices falls within established precedents for journalistic access to government information.

## OCR processing for Russian-language documents

Russian OCR presents unique challenges due to Cyrillic character recognition, legal document formatting, and potential scanning quality issues. **Tesseract with Russian language packs (`rus+eng` configuration)** provides foundational OCR capabilities, but document preprocessing significantly improves accuracy.

Implement image preprocessing pipeline including grayscale conversion, noise reduction through median filtering, and adaptive thresholding to optimize character recognition. Legal documents often contain stamps, signatures, and formatting elements that interfere with text extraction, requiring sophisticated preprocessing techniques.

**Hybrid processing strategy** attempts direct PDF text extraction first, falling back to OCR for scanned documents. PyMuPDF enables efficient text extraction from native PDFs, while pdf2image converts scanned documents for OCR processing. This approach optimizes processing speed while ensuring comprehensive text extraction.

Quality validation combines technical metrics (OCR confidence scores) with linguistic analysis (Russian character ratios, legal terminology presence). Documents with quality scores below 75% should trigger manual review workflows. Implement automated spell-checking against Russian legal dictionaries to identify and correct common OCR errors.

For critical legal documents, **maintain both original document images and extracted text with version control** to support legal admissibility requirements. Hash verification ensures document integrity throughout the processing pipeline.

## Legal and ethical framework for evidence collection

War crimes documentation requires adherence to **Berkeley Protocol standards for digital open source investigations**, establishing international guidelines for evidence collection, authentication, and preservation. The protocol provides comprehensive frameworks for maintaining legal admissibility while protecting sources and investigators.

Jurisdictional complexity surrounding non-recognized occupation authorities creates legal challenges, but **universal jurisdiction for war crimes** enables evidence collection for international legal proceedings. Focus on publicly available information to minimize legal risks while following established precedents for journalistic access to government documents.

**Evidence standards for International Criminal Court** proceedings require comprehensive chain-of-custody documentation, technical authentication of digital materials, and expert witness capabilities for technical verification. The ICC's Project Harmony and OTPLink platforms demonstrate increasing acceptance of digital evidence when properly authenticated.

Data protection compliance requires implementing privacy-by-design principles while recognizing public interest exceptions for war crimes documentation. **GDPR Article 6 legitimate interest provisions** may justify processing of personal data for accountability purposes, but anonymization of non-essential personal identifiers remains critical.

Technical security measures should include end-to-end encryption for all communications, secure data storage with access controls, and anonymous web scraping techniques using VPN and proxy rotation. **Multi-factor authentication and role-based access controls** protect sensitive evidence while enabling collaborative investigation workflows.

## Proven methodologies from similar projects

**Bellingcat's TimeMap methodology** demonstrates effective approaches to systematic war crimes documentation, combining automated data collection with rigorous verification standards. Their documentation of 1,094+ bombing incidents in Ukraine provides scalable models for evidence aggregation and legal admissibility standards.

The **Syrian Archive's digital evidence workflow** offers proven techniques for large-scale document processing and verification, handling 2.5+ million videos through automated processing combined with human verification. Their approach to Arabic dialect analysis for location verification provides models for linguistic authentication techniques applicable to Russian-language materials.

**International Criminal Journalism Consortium (ICIJ) collaborative methodologies** demonstrate effective frameworks for international investigative partnerships. Their "Datashare" platform and secure communication protocols enable distributed teams to collaborate on sensitive investigations while maintaining source protection and data security.

UC Berkeley Human Rights Center's Berkeley Protocol represents the **international gold standard for digital evidence collection**, providing detailed technical and legal guidelines that have been adopted by UN human rights mechanisms and international criminal courts.

Technical implementation examples from the OSINT community, including **SpiderFoot's automated collection modules and Maltego's graph analysis capabilities**, provide open-source tools for systematic data collection and relationship analysis applicable to property seizure investigations.

## Repository structure and collaborative workflows

**Security-first repository architecture** separates public methodology documentation from private evidence collections, using role-based access controls for different sensitivity levels. Public repositories should contain analytical code, documentation, and tools while maintaining private repositories for sensitive data and ongoing investigations.

Implement modular structure following data science best practices: `/data/` for datasets with appropriate encryption, `/src/` for processing scripts, `/notebooks/` for analytical documentation, `/docs/` for methodology transparency, and `/tests/` for automated validation pipelines. **Each component should maintain independent version control** enabling selective sharing of methodologies without exposing sensitive evidence.

Documentation standards must meet both journalistic transparency requirements and legal admissibility standards. Maintain comprehensive records of data sources, processing methodologies, analytical decisions, and verification procedures. **Great Expectations framework** provides automated data validation capabilities essential for maintaining evidence integrity at scale.

Collaborative workflows require secure communication platforms (Signal for messaging, encrypted file sharing systems) combined with systematic verification procedures. The ICIJ's "radical sharing" philosophy demonstrates effective models for real-time collaboration while maintaining operational security for sensitive investigations.

**Multi-tiered backup strategies** using BD-R HTL media for 100+ year preservation of critical evidence, combined with encrypted cloud storage for operational access and offline storage for security. Implement 3-2-1 backup principles with regular verification and restoration testing.

## Critical implementation recommendations

Begin with **foundational security infrastructure** implementing encrypted communications, secure data storage, and access controls before handling sensitive evidence. Security breaches could endanger sources, compromise investigations, and render evidence inadmissible in legal proceedings.

**Establish partnerships with established investigative organizations** including Bellingcat, Syrian Archive, or academic human rights centers to leverage existing expertise and validation networks. These partnerships provide access to proven methodologies, technical resources, and legal expertise essential for credible war crimes documentation.

Implement **automated data validation pipelines** from the outset, combining technical quality checks with linguistic validation and cross-referencing against authoritative sources. Manual verification becomes impractical at scale, requiring robust automated systems with human oversight for edge cases.

**Legal consultation throughout development** ensures compliance with international evidence standards, jurisdiction-specific requirements, and ethical guidelines for investigative journalism in conflict zones. Regular consultation with media attorneys familiar with international criminal law provides essential guidance for evidence handling procedures.

Focus on **reproducible methodologies with comprehensive documentation** enabling independent verification and peer review. Transparent methodologies enhance credibility while enabling other investigators to build upon the work and verify findings through independent analysis.

This systematic approach to building comprehensive property seizure documentation capabilities provides a foundation for gathering court-admissible evidence while maintaining the highest standards of investigative journalism ethics and technical security. The combination of proven methodologies from established projects, robust technical architecture, and strict adherence to legal and ethical frameworks creates a powerful tool for documenting systematic war crimes and supporting accountability efforts.