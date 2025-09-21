# Contributing to Heimdall MCP Server

Thank you for your interest in contributing to Heimdall! This document outlines how to contribute to the project and explains our dual licensing model.

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Docker and Docker Compose
- Git

### Development Setup
1. Fork the repository
2. Clone your fork: `git clone https://github.com/your-username/cognitive-memory.git`
3. Create a virtual environment: `python -m venv venv && source venv/bin/activate`
4. Install dependencies: `pip install -e .[dev]`
5. Initialize the project: `heimdall project init`
6. Run tests: `pytest tests/`

## 📋 Contribution Process

### 1. Before You Start
- Check existing issues and PRs to avoid duplicates
- For major changes, open an issue first to discuss the approach
- All contributions must target the `dev` branch (not `main`)

### 2. Making Changes
- Create a feature branch: `git checkout -b feature/your-feature-name`
- Make your changes following the code style guidelines
- Add tests for new functionality
- Update documentation as needed
- Ensure all tests pass: `pytest tests/`

### 3. Submitting Changes
- Push your changes to your fork
- Open a Pull Request targeting the `dev` branch
- Fill out the PR template completely
- **First-time contributors**: Add a comment stating "I have read and agree to the CLA"

### 4. Code Review
- All PRs require maintainer approval
- CI checks must pass (linting, type checking, tests)
- Address any feedback promptly

## 🎯 Code Style Guidelines

### Python Code
- Follow PEP 8 style guidelines
- Use type hints for all functions and methods
- Maximum line length: 88 characters
- Use `ruff` for linting and formatting
- Pass `mypy` type checking

### Testing
- Write unit tests for new functionality
- Integration tests for complex workflows
- Maintain test coverage for modified code
- Use descriptive test names

### Documentation
- Update docstrings for new/modified functions
- Update `CLAUDE.md` for architectural changes
- Update CLI help text for new commands

## 📜 Licensing Model

### Dual Licensing Strategy
This project uses a **dual licensing model** to balance open source community benefits with sustainable commercial development:

**Open Source License (Apache 2.0)**
- Core functionality remains open source
- Community can use, modify, and distribute freely
- Contributions welcome from everyone

**Commercial Licensing**
- Future commercial features and services
- Enterprise support and hosting
- Custom integrations and consulting

### Contributor License Agreement (CLA)
All contributors must agree to our [Contributor License Agreement](CLA.md) which:
- Allows the project to offer commercial licenses
- Protects both contributors and the project
- Ensures your contributions remain open source
- Enables sustainable project development

### What This Means for You
- Your contributions will always be available under Apache 2.0
- The maintainer may use contributions in commercial offerings
- You retain copyright to your contributions
- You can always use your contributions under Apache 2.0

## 🐛 Bug Reports

When reporting bugs, please include:
- Steps to reproduce the issue
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)
- Relevant logs or error messages

## 💡 Feature Requests

For new features:
- Describe the problem you're trying to solve
- Explain your proposed solution
- Consider backward compatibility
- Discuss potential commercial implications

## 🔧 Development Commands

```bash
# Code quality
ruff check                    # Lint code
ruff format                   # Format code
mypy .                       # Type checking

# Testing
pytest tests/                # Run all tests
pytest -k "not slow"         # Skip slow tests

# Project management
heimdall project init        # Initialize development environment
heimdall doctor              # Check system health
```

## 📞 Getting Help

- **Issues**: Use GitHub Issues for bugs and feature requests
- **Discussions**: Use GitHub Discussions for questions and ideas
- **Email**: For security issues or private matters

## 🙏 Recognition

Contributors are recognized in:
- GitHub contributors list
- Release notes for significant contributions
- Project documentation

---

By contributing to this project, you agree to abide by our Code of Conduct and accept the terms of our [Contributor License Agreement](CLA.md).

Thank you for helping make Heimdall better! 🎉
