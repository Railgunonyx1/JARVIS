#!/usr/bin/env python
with open('core/agent/loop.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find the model selection section and add confidence-based cascade logic
old_section = """# Model Gateway: select model based on harness requirements
            if self._model_gateway is not None:
                _t_ms = time.time()
                requirements = set()
                if self._harness is not None:
                    for pref in self._harness.config.model_preference:
                        from providers.model_gateway import Capability
                        try:
                            requirements.add(Capability(pref))
                        except ValueError:
                            pass
                profile = self._model_gateway.select(
                    requirements=requirements or None,
                    session_id=session_id or None,
                    confidence=classified.confidence,
                )"""

new_section = """# Model Gateway: select model based on harness requirements
            # with confidence-based cascade fallback
            if self._model_gateway is not None:
                _t_ms = time.time()
                requirements = set()
                if self._harness is not None:
                    for pref in self._harness.config.model_preference:
                        from providers.model_gateway import Capability
                        try:
                            requirements.add(Capability(pref))
                        except ValueError:
                            pass
                # Try primary model selection with confidence
                profile = self._model_gateway.select(
                    requirements=requirements or None,
                    session_id=session_id or None,
                    confidence=classified.confidence,
                )
                
                # Confidence-based cascade: if confidence is low or profile is None,
                # fall back to less expensive models
                if profile is None or classified.confidence < 0.5:
                    # Try secondary models with lower precision but faster speed
                    secondary_requirements = requirements.copy()
                    # Add secondary model preferences
                    if self._harness is not None:
                        for pref in list(self._harness.config.model_preference)[1:3]:
                            from providers.model_gateway import Capability
                            try:
                                secondary_requirements.add(Capability(pref))
                            except ValueError:
                                pass
                    profile = self._model_gateway.select(
                        requirements=secondary_requirements or None,
                        session_id=session_id or None,
                        confidence=max(classified.confidence, 0.3),  # minimum threshold
                    )
                
                # If still no profile, try the most lightweight model available
                if profile is None:
                    lightweight_requirements = set()
                    if self._harness is not None:
                        for pref in self._harness.config.model_preference[-2:]:
                            from providers.model_gateway import Capability
                            try:
                                lightweight_requirements.add(Capability(pref))
                            except ValueError:
                                pass
                    profile = self._model_gateway.select(
                        requirements=lightweight_requirements or None,
                        session_id=session_id or None,
                        confidence=0.2,  # absolute minimum
                    )"""

if old_section in content:
    new_content = content.replace(old_section, new_section)
    with open('core/agent/loop.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Confidence-based cascade added successfully')
else:
    print('Old section not found - showing first 100 chars around area:')
    idx = content.find('# Model Gateway: select model')
    if idx >= 0:
        print(content[idx:idx+500])